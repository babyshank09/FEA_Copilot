import json
import os 
import pickle
import time
from collections import defaultdict
from typing import List, Literal, Optional

from cohere.errors.too_many_requests_error import TooManyRequestsError
from langchain_chroma import Chroma
from langchain_classic.retrievers import EnsembleRetriever
from langchain_cohere import CohereRerank
from langchain_community.retrievers import BM25Retriever 
from langchain_core.documents import Document
from pydantic import BaseModel, Field 

from src.backend.config.config import BACKEND_DIR
from src.backend.config.logging_config import DEBUG, procedural_rag_logger, scripting_rag_logger
from src.backend.rag.ingestion_pipeline import IngestionPipeline
from src.backend.llm.azure_llm_reasoning import get_rag_query_llm




RagTargetType = Literal["procedural", "scripting"]
RetrieverType = Literal["hybrid", "vector"]
VectorRetrieverType = Literal["similarity", "similarity_score_threshold", "mmr"]


class QueryVariations(BaseModel):
    queries: List[str] = Field(
        min_length=5, 
        max_length=5,
        description="""
            Exactly five standalone search queries that preserve the same meaning as the user's question.
            The first query must be the original user query unchanged, and the remaining four must be
            semantically equivalent variations optimized for search retrieval.
        """
    )


class RetrievalPipeline:  

    def __init__(self, vectorstore: Chroma, rag_target: RagTargetType, log: bool = False): 
        self.log = log
        self.rag_target = rag_target

        if rag_target == "scripting":
            self.collection_name = "abaqus_scripting_docs"
            self.logger = scripting_rag_logger
        else:
            self.collection_name = "procedural_docs"
            self.logger = procedural_rag_logger
            
        self.vectorstore = vectorstore
        self.llm = get_rag_query_llm()
        self.reranker = CohereRerank(model="rerank-english-v3.0", top_n=3, cohere_api_key=os.getenv("CO_API_KEY")) 

        self.bm25_path = os.path.join(BACKEND_DIR, f"vectorstore/bm25_retrievers/{rag_target}_bm25.pkl")
        os.makedirs(os.path.dirname(self.bm25_path), exist_ok=True)

        self.bm25_retriever = self.load_bm25_retriever()



    def get_embedded_filenames(self) -> List[str]: 
        existing = self.vectorstore.get(include=["metadatas"])
        embedded_filenames = list(
            set(
                metadata.get("source") 
                for metadata in existing.get("metadatas", []) 
                if metadata and metadata.get("source")
            )
        )
        self.logger.info(f"Files already embedded in vectorstore: {embedded_filenames}")
        return embedded_filenames



    def get_bm25_filenames(self, bm25_retriever: BM25Retriever) -> List[str]:
        if not bm25_retriever or not hasattr(bm25_retriever, "docs"):
            self.logger.warning(" BM25 retriever is not loaded or has no documents.")
            return []

        bm25_filenames = list(
            set(
                doc.metadata.get("source") 
                for doc in bm25_retriever.docs 
                if doc.metadata and doc.metadata.get("source")
            )
        )
        self.logger.info(f"Files indexed in BM25 retriever: {bm25_filenames}")
        return bm25_filenames



    def is_bm25_synced_with_vectorstore(self, bm25_retriever: BM25Retriever) -> bool:
        embedded_filenames = set(self.get_embedded_filenames())
        bm25_filenames = set(self.get_bm25_filenames(bm25_retriever))

        if embedded_filenames != bm25_filenames:
            missing_in_bm25 = embedded_filenames - bm25_filenames
            missing_in_vectorstore = bm25_filenames - embedded_filenames

            if missing_in_bm25:
                self.logger.warning(f" Files in vectorstore but missing from BM25: {missing_in_bm25}")
            if missing_in_vectorstore:
                self.logger.warning(f" Files in BM25 but missing from vectorstore: {missing_in_vectorstore}")

            return False

        self.logger.info("  BM25 retriever is in sync with vectorstore.")
        return True



    def save_bm25_retriever(self, bm25_retriever: BM25Retriever):
        os.makedirs(os.path.dirname(self.bm25_path), exist_ok=True)
        with open(self.bm25_path, "wb") as f:
            pickle.dump(bm25_retriever, f)
        self.logger.info(f"  Saved BM25 retriever to {self.bm25_path}")



    def build_bm25_from_vectorstore(self) -> BM25Retriever:
        vectorstore_data = self.vectorstore.get(
            include=["documents", "metadatas"]
        )
        chunks = [
            Document(page_content=text, metadata=meta or {})
            for text, meta in zip(
                vectorstore_data["documents"], vectorstore_data["metadatas"]
            )
        ]
        if not chunks:
            self.logger.warning(" No documents found in vectorstore to construct BM25 retriever.")
            chunks = [Document(page_content="placeholder_empty_vectorstore", metadata={"source": "dummy"})]

        bm25_retriever = BM25Retriever.from_documents(documents=chunks)
        bm25_retriever.k = 10
        return bm25_retriever



    def refresh_bm25(self) -> BM25Retriever:
        self.logger.info("Refreshing BM25 index from vectorstore...")
        self.bm25_retriever = self.build_bm25_from_vectorstore()
        self.save_bm25_retriever(self.bm25_retriever)
        self.logger.info(
            f"BM25 refreshed -- {len(self.bm25_retriever.docs)} chunks, "
            f"sources: {self.get_bm25_filenames(self.bm25_retriever)}"
        )
        return self.bm25_retriever



    def load_bm25_retriever(self) -> BM25Retriever:
        if os.path.exists(self.bm25_path):
            self.logger.info(f"Loading BM25 retriever from {self.bm25_path}...")
            with open(self.bm25_path, "rb") as f:
                bm25_retriever = pickle.load(f)
                bm25_retriever.k = 10
            
            if self.is_bm25_synced_with_vectorstore(bm25_retriever):
                return bm25_retriever
            else:
                self.logger.warning(" BM25 is out of sync with vectorstore. Rebuilding...")
                bm25_retriever = self.build_bm25_from_vectorstore()
                self.save_bm25_retriever(bm25_retriever)
                return bm25_retriever
        else:
            self.logger.warning(f" BM25 pickle file not found at {self.bm25_path}. Building dynamically from vectorstore...")
            bm25_retriever = self.build_bm25_from_vectorstore()
            self.save_bm25_retriever(bm25_retriever)
            return bm25_retriever



    def generate_query_variations(self, original_query: str) -> List[str]:
        self.logger.info("Generating query variations using LLM...")
        self.logger.info(f"Original Query: {original_query}\n")   

        query_llm = self.llm.with_structured_output(QueryVariations)

        prompt = f"""
        Generate 4 different variations of this query that would help retrieve relevant documents:
        Original query: {original_query}

        Return 4 alternative queries that rephrase or approach the same question from different angles along with the original user query. So in total you have to return 5 queries - the original one and 4 variations. 
        """
        
        try:
            response = query_llm.invoke(prompt)
            query_variations = response.queries  

            self.logger.info("Generated Query Variations:")
            for i, variation in enumerate(query_variations, 1):
                self.logger.info(f"{i}. {variation}")

            return query_variations 

        except Exception as e:
            self.logger.error(f"Error occurred while generating multiple queries for retrieval: {str(e)}")
            raise e 



    def retrieve_chunks_for_multiple_queries(self, queries: List[str], retriever) -> List[List[Document]]: 
        all_retrieval_chunks = [] 

        for i, query in enumerate(queries, 1): 
            self.logger.info(f"Retrieving relevant chunks for query {i}: {query}")
            chunks = retriever.invoke(query) 
            if not chunks:
                self.logger.warning("No relevant chunks found")
            all_retrieval_chunks.append(chunks)     
        
        self.logger.info("Multi-Query Retrieval Complete!")
        return all_retrieval_chunks



    def reciprocal_rank_fusion(self, chunk_lists: List[List[Document]], k: int = 60) -> List[Document]: 
        rrf_scores = defaultdict(float)  
        all_unique_chunks = {} 
        chunk_id_map = {} 
        chunk_counter = 1 

        if not chunk_lists:
            return []
        
        for i, query_chunks in enumerate(chunk_lists, 1):
            self.logger.info(f"Processing chunks for query {i} with {len(query_chunks)} retrieved documents.")
            
            for position, chunk in enumerate(query_chunks, 1): 
                chunk_content = chunk.page_content 

                if chunk_content not in chunk_id_map: 
                    chunk_id_map[chunk_content] = f"Chunk_{chunk_counter}"
                    all_unique_chunks[chunk_content] = chunk 
                    chunk_counter += 1 

                chunk_id = chunk_id_map[chunk_content]
                position_score = 1 / (k + position)

                rrf_scores[chunk_content] += position_score

                self.logger.info(f"  Position {position}: {chunk_id} +{position_score:.4f} (running total: {rrf_scores[chunk_content]:.4f})")
                self.logger.info(f"  Preview: {chunk_content[:80]}...")

        sorted_chunks = sorted(
            [(all_unique_chunks[chunk_content], score) for chunk_content, score in rrf_scores.items()], 
            key=lambda x: x[1], 
            reverse=True
        )

        rrf_chunks = [chunk for chunk, score in sorted_chunks]

        self.logger.info(f"  RRF Complete! Selected {len(sorted_chunks)} unique chunks from {len(chunk_lists)} queries.")

        if self.log:
            filepath = os.path.join(BACKEND_DIR, f"debugging/retrieval_stage/{self.rag_target}_reciprocal_rank_fusion_results.json")
            os.makedirs(os.path.dirname(filepath), exist_ok=True)

            with open(filepath, 'w', encoding='utf-8') as f:
                chunk_list = [
                    {
                        "chunk_id": chunk_id_map[chunk.page_content],
                        "page_content": chunk.page_content,
                        "metadata": chunk.metadata,
                        "rrf_score": score
                    }
                    for chunk, score in sorted_chunks
                ]
                json.dump(chunk_list, f, indent=2, ensure_ascii=False)

        return rrf_chunks


  
    def create_retriever(self, retriever_type: RetrieverType = "hybrid", vector_retriever_type: VectorRetrieverType = "similarity_score_threshold", source_file: Optional[str] = None): 
        self.logger.info(f"Creating a {retriever_type} retriever with vector retriever type: {vector_retriever_type}...")

        search_kwargs = {"k": 9}
        if source_file:
            search_kwargs["filter"] = {"source": {"$contains": source_file}}
        
        def get_vector_retriever(vector_type: str):
            if vector_type == "similarity":
                return self.vectorstore.as_retriever(search_kwargs=search_kwargs)  
            
            elif vector_type == "similarity_score_threshold": 
                kwargs = {**search_kwargs, "score_threshold": 0.3}
                return self.vectorstore.as_retriever(
                    search_type="similarity_score_threshold",
                    search_kwargs=kwargs
                )
                 
            elif vector_type == "mmr": 
                kwargs = {**search_kwargs, "fetch_k": 10, "lambda_mult": 0.5}
                return self.vectorstore.as_retriever(
                    search_type="mmr",
                    search_kwargs=kwargs
                )
            return self.vectorstore.as_retriever(search_kwargs=search_kwargs)


        
        def get_keyword_retriever(): 
            if source_file:
                filtered_docs = [
                    doc 
                    for doc in self.bm25_retriever.docs 
                    if source_file in doc.metadata.get("source", "") and doc.page_content.strip()
                ]
                if not filtered_docs:
                    self.logger.warning(
                        f" No BM25 documents matched source_file: {source_file}"
                    )
                    return self.bm25_retriever
                
                filtered_bm25_retriever = BM25Retriever.from_documents(filtered_docs)
                filtered_bm25_retriever.k = 10
                return filtered_bm25_retriever
        
            return self.bm25_retriever


        
        def get_hybrid_retriever():
            vector_retriever = get_vector_retriever(vector_type=vector_retriever_type)
            keyword_retriever = get_keyword_retriever() 

            return EnsembleRetriever(
                retrievers=[vector_retriever, keyword_retriever], 
                weights=[0.7, 0.3]
            )

        if retriever_type == "vector": 
            retriever = get_vector_retriever(vector_type=vector_retriever_type) 
        elif retriever_type == "hybrid": 
            retriever = get_hybrid_retriever()
        else:
            retriever = get_hybrid_retriever()
                
        self.logger.info(f"  Created a {retriever_type} retriever with vector retriever type: {vector_retriever_type} successfully")
        return retriever



    def rerank_chunks(self, chunks: List[Document], reranking_query: str) -> List[Document]: 
        if reranking_query is None:
            self.logger.warning("No reranking query available. Returning original chunk order") 
            return chunks 

        if not chunks:
            return []
        
        self.logger.info("Reranking chunks...") 
        max_retries = 3
        for attempt in range(max_retries):
            try:
                reranked_docs = self.reranker.compress_documents(query=reranking_query, documents=chunks) 

                if self.log:
                    filepath = os.path.join(BACKEND_DIR, f"debugging/retrieval_stage/{self.rag_target}_reranked_chunks.json")
                    os.makedirs(os.path.dirname(filepath), exist_ok=True)
                    
                    with open(filepath, 'w', encoding='utf-8') as f:
                        chunk_list = [
                            {
                                "chunk_id": f"Reranked_Chunk_{i}",
                                "page_content": chunk.page_content,
                                "metadata": chunk.metadata,
                                "reranking_query": reranking_query
                            }
                            for i, chunk in enumerate(reranked_docs, 1)
                        ]
                        json.dump(chunk_list, f, indent=2, ensure_ascii=False) 
            
                self.logger.info(f"Reranking complete! Exported reranked chunks to {self.rag_target}_reranked_chunks.json")
                return reranked_docs
            
            except TooManyRequestsError:
                wait = 60 * (attempt + 1)  
                self.logger.warning(f"Cohere rate limit hit. Waiting {wait}s before retry {attempt+1}/{max_retries}...")
                time.sleep(wait)

        self.logger.warning("❌ Cohere reranker failed after all retries — returning unranked chunks.")
        return chunks



    def export_retrieved_chunks_to_json(self, chunks: List[Document], retrieval_method: str):
        filename: str = f"{self.rag_target}_retrieved_chunks.json"
        filepath = os.path.join(BACKEND_DIR, "debugging/retrieval_stage", filename)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        export_data = [
            {
                "chunk_id": i + 1,
                "page_content": doc.page_content,
                "metadata": doc.metadata,
                "retrieval_method": retrieval_method
            }
            for i, doc in enumerate(chunks)
        ]

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"Exported {len(export_data)} chunks to {filename}")
        return export_data 



    def run_simple_retrieval_pipeline(self, query: str, retriever_type: RetrieverType = "hybrid", vector_retriever_type: VectorRetrieverType = "similarity_score_threshold") -> List[Document]: 
        self.logger.info("Starting simple retrieval pipeline...")
        retriever = self.create_retriever(retriever_type=retriever_type, vector_retriever_type=vector_retriever_type)  

        self.logger.info(f"Retrieving relevant chunks for query: {query}")
        chunks = retriever.invoke(query) 

        if self.log:
            self.export_retrieved_chunks_to_json(chunks=chunks, retrieval_method=retriever_type) 
        self.logger.info("Simple retrieval pipeline completed successfully!")

        return chunks



    def run_retrieval_pipeline(self, query: str, retriever_type: RetrieverType = "hybrid", vector_retriever_type: VectorRetrieverType = "similarity_score_threshold") -> List[Document]:  
        self.logger.info("Starting retrieval pipeline...")
        
        retriever = self.create_retriever(retriever_type=retriever_type, vector_retriever_type=vector_retriever_type)  
        query_variations = self.generate_query_variations(original_query=query)  
        all_retrieval_chunks = self.retrieve_chunks_for_multiple_queries(queries=query_variations, retriever=retriever) 
        rrf_chunks = self.reciprocal_rank_fusion(chunk_lists=all_retrieval_chunks) 
        reranked_chunks = self.rerank_chunks(chunks=rrf_chunks, reranking_query=query)

        if self.log:
            self.export_retrieved_chunks_to_json(chunks=reranked_chunks, retrieval_method=retriever_type) 

        self.logger.info("Retrieval pipeline completed successfully!") 
        return reranked_chunks or []




# if __name__ == "__main__": 
#     scripting_ingestion_pipeline = IngestionPipeline(rag_target="scripting", log=DEBUG) 
#     procedural_ingestion_pipeline = IngestionPipeline(rag_target="procedural", log=DEBUG) 

#     scripting_ingestion_pipeline.run_ingestion_pipeline()
#     procedural_ingestion_pipeline.run_ingestion_pipeline()

#     # procedural_ingestion_pipeline.delete_chunks_by_source(source_filename = "test_rag_doc.pdf", source_abs_path=r"/Users/shankar/Documents/Perfect_Environment/Agentic_AI/Abaqus_CAE_Copilot/src/backend/assets/training_docs/procedural_docs/test_rag_doc.pdf") 
#     # scripting_ingestion_pipeline.delete_chunks_by_source(source_filename = "RelievingLetter.pdf", source_abs_path=r"/Users/shankar/Documents/Perfect_Environment/Agentic_AI/Abaqus_CAE_Copilot/src/backend/assets/training_docs/scripting_docs/RelievingLetter.pdf") 


#     scripting_retrieval_pipeline = RetrievalPipeline(rag_target="scripting", vectorstore=scripting_ingestion_pipeline.vectorstore, log=DEBUG)
#     procedural_retrieval_pipeline = RetrievalPipeline(rag_target="procedural", vectorstore=procedural_ingestion_pipeline.vectorstore, log=DEBUG)

#     scripting_query = "how can i mesh a model"
#     # procedural_query = "The user has asked to form a connection between two surfaces"

#     scripting_retrieval_pipeline.run_retrieval_pipeline(query=scripting_query, retriever_type="hybrid", vector_retriever_type="similarity_score_threshold")
#     # procedural_retrieval_pipeline.run_retrieval_pipeline(query=procedural_query, retriever_type="hybrid", vector_retriever_type="similarity_score_threshold")