import os
import shutil
import csv
from io import StringIO
from datetime import datetime

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
# --- PERUBAHAN IMPORT ---
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from dotenv import load_dotenv

# Membaca API Key dari file .env
load_dotenv(dotenv_path="../.env")

app = FastAPI()

# Mengaktifkan CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 1. Variabel Global dan Setup Awal
DB_DIR = "./db"
DATASET_DIR = "../dataset"

os.makedirs(DATASET_DIR, exist_ok=True)

embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
vector_store = Chroma(persist_directory=DB_DIR, embedding_function=embeddings)

# --- INISIALISASI LLM ---
llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    groq_api_key=os.getenv("GROQ_API_KEY")
)

# Default System Prompt
custom_system_prompt = (
    "Kamu adalah asisten akademik Student Service Center (SSC) Telkom University Surabaya. "
    "Gunakan dokumen pedoman akademik berikut untuk menjawab pertanyaan mahasiswa secara ramah. "
    "Selalu sebutkan sumber informasinya (contoh: 'Berdasarkan Pedoman Akademik...'). "
    "Jika jawabannya tidak ada di dalam dokumen, katakan saja kamu tidak tahu.\n\n"
    "{context}"
)

chat_history = []

# ... (Endpoint /upload tetap sama)
@app.post("/upload")
async def upload_pdf(file: UploadFile = File(None), prompt: str = Form(None)):
    global custom_system_prompt, vector_store
    if prompt:
        custom_system_prompt = prompt + "\n\n{context}"
    if file:
        try:
            vector_store.delete_collection()
        except Exception:
            pass
        file_path = f"{DATASET_DIR}/{file.filename}"
        with open(file_path, "wb") as f:
            f.write(await file.read())
        loader = PyPDFLoader(file_path)
        docs = loader.load()
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        splits = text_splitter.split_documents(docs)
        vector_store = Chroma.from_documents(documents=splits, embedding=embeddings, persist_directory=DB_DIR)
        return {"status": "success", "message": f"Pedoman {file.filename} berhasil diperbarui!"}
    return {"status": "success", "message": "Instruksi karakter bot berhasil diupdate!"}

# ... (Endpoint /tanya tetap sama)
@app.post("/tanya")
async def tanya_bot(data: dict):
    pertanyaan = data.get("pertanyaan")
    retriever = vector_store.as_retriever()
    prompt_template = ChatPromptTemplate.from_messages([
        ("system", custom_system_prompt),
        ("human", "{input}"),
    ])
    def format_docs(docs):
        return "\n\n".join(doc.page_content for doc in docs)
    rag_chain = (
        {"context": retriever | format_docs, "input": RunnablePassthrough()}
        | prompt_template
        | llm
        | StrOutputParser()
    )
    response = rag_chain.invoke(pertanyaan)
    waktu = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    chat_history.append({"waktu": waktu, "pertanyaan": pertanyaan, "jawaban": response})
    return {"jawaban": response}

# ... (Endpoint health, export, documents, dan delete tetap sama)
@app.get("/health")
async def health_check():
    return {"status": "ok", "backend": "online", "database": "online"}

@app.get("/export-logs")
async def export_logs():
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=["waktu", "pertanyaan", "jawaban"])
    writer.writeheader()
    writer.writerows(chat_history)
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=log_chatbot_ssc.csv"})

@app.get("/documents")
async def get_documents():
    files = []
    if os.path.exists(DATASET_DIR):
        for f in os.listdir(DATASET_DIR):
            if f.endswith(".pdf"):
                file_path = os.path.join(DATASET_DIR, f)
                timestamp = os.path.getmtime(file_path)
                date_str = datetime.fromtimestamp(timestamp).strftime("%d %b %Y")
                files.append({"nama_file": f, "tanggal": date_str})
    return {"documents": files}

@app.delete("/documents/{filename}")
async def delete_document(filename: str):
    file_path = os.path.join(DATASET_DIR, filename)
    if os.path.exists(file_path):
        os.remove(file_path)
        try:
            vector_store.delete_collection()
        except Exception:
            pass
        return {"status": "success", "message": f"File {filename} dan memori AI berhasil dihapus!"}
    return {"status": "error", "message": "File tidak ditemukan."}

# 3. Endpoint Tanya Bot
@app.post("/tanya")
async def tanya_bot(data: dict):
    pertanyaan = data.get("pertanyaan")
    
    try:
        retriever = vector_store.as_retriever()
        
        prompt_template = ChatPromptTemplate.from_messages([
            ("system", custom_system_prompt),
            ("human", "{input}"),
        ])
        
        def format_docs(docs):
            return "\n\n".join(doc.page_content for doc in docs)
        
        rag_chain = (
            {"context": retriever | format_docs, "input": RunnablePassthrough()}
            | prompt_template
            | llm
            | StrOutputParser()
        )
        
        response = rag_chain.invoke(pertanyaan)

    except ValueError as e:
        # Menangkap error jika database benar-benar kosong / belum diinisialisasi
        if "Chroma collection not initialized" in str(e):
            response = "Maaf, saat ini belum ada dokumen pedoman atau pengumuman yang tersedia di sistem. Silakan hubungi Admin SSC untuk mengunggah dokumen terlebih dahulu."
        else:
            response = "Maaf, terjadi kesalahan internal pada memori database."
    except Exception as e:
        # Menangkap error umum lainnya (misal API ngadat)
        response = "Maaf, sistem asisten saat ini sedang sibuk atau mengalami gangguan."

    # Menyimpan percakapan ke riwayat untuk analitik dashboard
    waktu = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    chat_history.append({"waktu": waktu, "pertanyaan": pertanyaan, "jawaban": response})

    return {"jawaban": response}
