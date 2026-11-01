import json
import os 
from typing import Literal

from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from dotenv import load_dotenv  

from src.backend.config.logging_config import DEBUG, procedural_rag_logger, scripting_rag_logger
from src.backend.config.config import BACKEND_DIR, ASSETS_DIR

load_dotenv() 
RagTargetType = Literal["procedural", "scripting"]



class IngestionPipeline: 

    def __init__(self, rag_target: RagTargetType, log: bool = False): 
        self.rag_target = rag_target
        if rag_target == "scripting":
            self.collection_name = "abaqus_scripting_docs"
            self.logger = scripting_rag_logger
        else:
            self.collection_name = "procedural_docs"
            self.logger = procedural_rag_logger

        self.persist_directory = os.path.join(BACKEND_DIR, "vectorstore/chroma_db_production")
        self.log = log
        
        debug_dirs = [
            "debugging/ingestion_stage",
            "debugging/retrieval_stage",
            "debugging/response_synthesis_stage",
        ]

        for path in debug_dirs:
            os.makedirs(os.path.join(BACKEND_DIR, path), exist_ok=True)

        self.embeddings = OpenAIEmbeddings(model = "text-embedding-3-small", openai_api_key = os.getenv("OPENAI_API_KEY")) 
        self.vectorstore = Chroma(
            collection_name = self.collection_name,
            embedding_function = self.embeddings,
            persist_directory = self.persist_directory,
            collection_metadata={"hnsw:space": "cosine"}
        )



    def create_text_chunks(self, pdf_file_path):
        loader = PyPDFLoader(pdf_file_path)
        pages = loader.load()  

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=5000,
            chunk_overlap=1000
        )

        chunks = splitter.split_documents(pages)

        for chunk in chunks:
            chunk.metadata["source"] = os.path.basename(chunk.metadata.get("source", "Unknown"))
            source = chunk.metadata.get("source", "Unknown")
            page = chunk.metadata.get("page_label", "Unknown")

            chunk.page_content = (
                f"Source: {source}\n"
                f"Page: {page}\n\n"
                f"{chunk.page_content}"
            )

        return chunks
    


    def export_chunks_to_json(self, chunks, filename="chunks_export.json"):
        filepath = os.path.join(BACKEND_DIR, "debugging/ingestion_stage", filename)

        export_data = []
        
        for i, doc in enumerate(chunks):
            chunk_data = {
                "chunk_id": i + 1,
                "page_content": doc.page_content,
                "metadata": doc.metadata
            }
            export_data.append(chunk_data)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"Exported {len(export_data)} chunks to {filename}")
        return export_data 
    
    
    
    def get_scripting_docs_filenames(self): 
        scripting_docs_dir = os.path.join(BACKEND_DIR, "assets/training_docs/scripting_docs")
        user_docs_dir = os.path.join(ASSETS_DIR, "user_uploaded_docs")
        
        scripting_docs_paths = [
            os.path.abspath(os.path.join(scripting_docs_dir, f)) 
            for f in os.listdir(scripting_docs_dir) 
            if not f.startswith('.')
        ]
        
        user_uploaded_script_paths = [
            os.path.abspath(os.path.join(user_docs_dir, f)) 
            for f in os.listdir(user_docs_dir) 
            if not f.startswith('.')
        ]
        
        absolute_paths = scripting_docs_paths + user_uploaded_script_paths
        self.logger.info(f"Scripting docs(training + user) absolute file paths: {absolute_paths}")
        return absolute_paths



    def get_procedural_docs_filenames(self):
        procedural_dir = os.path.join(BACKEND_DIR, "assets/training_docs/procedural_docs")
        
        absolute_paths = [
            os.path.abspath(os.path.join(procedural_dir, f)) 
            for f in os.listdir(procedural_dir) 
            if not f.startswith('.')
        ]
        
        return absolute_paths



    def get_embedded_filenames(self): 
        existing = self.vectorstore.get(include=["metadatas"])
        embedded_filenames = list(set(metadata.get("source") for metadata in existing["metadatas"]))
        self.logger.info(f"Files already embedded in vectorstore: {embedded_filenames}")
        return embedded_filenames
    
    
    
    def get_processed_text_chunks(self, pdf_path):
        self.logger.info("Creating processed text chunks for: %s", pdf_path)
        try:
            chunks = self.create_text_chunks(pdf_file_path=pdf_path)
            self.logger.info("Created %d text chunks for %s", len(chunks), os.path.basename(pdf_path))
            return chunks
        
        except Exception:
            self.logger.exception("Failed to create text chunks for: %s", pdf_path)
            raise
          
        

    def delete_chunks_by_source(self, source_filename: str, source_abs_path:str = None):
        def delete_chunks_from_vectorstore():
            existing = self.vectorstore.get(include=["metadatas"])

            ids_to_delete = [
                    id_ for id_, md in zip(existing["ids"], existing["metadatas"])
                    if md.get("source") == source_filename
                ]

            if not ids_to_delete:
                return 
            
            self.vectorstore.delete(ids=ids_to_delete)
            self.logger.info(f"Deleted {len(ids_to_delete)} chunks from {source_filename}")

            current_embedded_filenames = self.get_embedded_filenames()
            self.logger.info(f"Current files embedded after deletion: {current_embedded_filenames}")  


        def delete_source_from_docs():
            if source_abs_path:
                docs_path = source_abs_path
            else:
                docs_path = os.path.join(ASSETS_DIR, "user_uploaded_docs", source_filename)
            
            if os.path.exists(docs_path): 
                os.remove(docs_path) 
                self.logger.info(f"Deleted source file from docs: {source_filename}")
            else:
                self.logger.warning(f"Could not delete {docs_path} as it does not exist")

        try:
            delete_chunks_from_vectorstore() 
            delete_source_from_docs()
        
        except Exception as e:
            self.logger.error(f"Error occured while deleting the file from vectorstore: {str(e)}")
            raise e

                  
    
    def run_ingestion_pipeline(self):
        self.logger.info("Starting RAG Text Ingestion Pipeline...")

        os.makedirs(self.persist_directory, exist_ok=True)
        stored_filenames = self.get_scripting_docs_filenames() if self.rag_target == "scripting" else self.get_procedural_docs_filenames()

        if not stored_filenames:
            self.logger.warning("Ingestion pipeline exited as there are no documents to ingest")
            return

        if os.path.exists(os.path.join(self.persist_directory, "chroma.sqlite3")):
            self.logger.info("Loaded existing vectorstore")

            embedded_filenames = self.get_embedded_filenames()

            for filepath in stored_filenames:
                filename = os.path.basename(filepath)
                if filename not in embedded_filenames:                                     
                    self.logger.info("New file detected: %s - embedding...", filename)
                    new_processed_chunks = self.get_processed_text_chunks(pdf_path=filepath) 
                    
                    if self.log:
                        self.export_chunks_to_json(chunks=new_processed_chunks, filename=f"{filename}_chunks.json")

                    self.vectorstore.add_documents(new_processed_chunks)
                    self.logger.info("Added %d chunks from %s", len(new_processed_chunks), filename)
                else:
                    self.logger.info("File %s already embedded - skipping...", filename)

        else:
            final_processed_chunks = []
            for filepath in stored_filenames:
                filename = os.path.basename(filepath)
                self.logger.info("File detected: %s - creating chunks...", filename)
                processed_chunks = self.get_processed_text_chunks(pdf_path=filepath) 

                if self.log:
                    self.export_chunks_to_json(chunks=processed_chunks, filename=f"{filename}_chunks.json")

                self.logger.info("Created %d chunks from %s", len(processed_chunks), filename)
                final_processed_chunks.extend(processed_chunks)

            self.logger.info("--- Creating vector store ---")
            self.vectorstore = Chroma.from_documents(
                collection_name=self.collection_name,
                documents=final_processed_chunks,
                embedding=self.embeddings,
                persist_directory=self.persist_directory,
                collection_metadata={"hnsw:space": "cosine"}
            )
            self.logger.info("Vector store created and saved to %s", self.persist_directory)

        self.logger.info("Pipeline completed successfully!")
    


# if __name__ == "__main__":
#     pipeline  = IngestionPipeline(rag_target = "scripting", log=DEBUG) 
#     pipeline.run_ingestion_pipeline()  

#     pipeline.delete_chunks_by_source(source_filename = "ChatGPT_Voice_Usage_Milestone_3.pdf", source_abs_path = "/Users/shankar/Documents/Perfect_Environment/Agentic_AI/Abaqus_CAE_Copilot/src/backend/assets/training_docs/scripting_docs/ChatGPT_Voice_Usage_Milestone_3.pdf") 
#     pipeline.delete_chunks_by_source(source_filename = "Sivashankar_Subramaniam_CV_2026_Final (2).pdf") 

    








        
