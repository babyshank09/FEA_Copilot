import os 
import logging

DEBUG = True
CURRENT_FILE = os.path.abspath(__file__)
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_FILE))

APP_LOG_FILE = os.path.join(PROJECT_ROOT, "debugging", "app_logs.log")
PROCEDURAL_RAG_LOG_FILE = os.path.join(PROJECT_ROOT, "debugging", "procedural_rag_logs.log")
SCRIPTS_RAG_LOG_FILE =  os.path.join(PROJECT_ROOT, "debugging", "scripting_rag_logs.log")

os.makedirs(os.path.join(PROJECT_ROOT, "debugging"), exist_ok = True)


def get_file_logger(logger_name: str, log_file_path: str, level=logging.INFO) -> logging.Logger:
    """
    Creates, configures, and returns a logger that writes ONLY to a specific file.
    """
    logger = logging.getLogger(logger_name)
    logger.setLevel(level)
    logger.propagate = False

    if not logger.handlers:
        log_dir = os.path.dirname(log_file_path)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)

        file_handler = logging.FileHandler(log_file_path)
        file_handler.setLevel(level)
        
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s')
        file_handler.setFormatter(formatter)

        logger.addHandler(file_handler)

    return logger


current_level = logging.INFO if DEBUG else logging.WARNING

app_logger = get_file_logger(logger_name="app", log_file_path=APP_LOG_FILE, level=current_level)
procedural_rag_logger = get_file_logger(logger_name="procedural_rag", log_file_path=PROCEDURAL_RAG_LOG_FILE, level=current_level)
scripting_rag_logger = get_file_logger(logger_name="scripts_rag", log_file_path=SCRIPTS_RAG_LOG_FILE, level=current_level)
