# AI Concierge 24/7 — Vietnam Luxury Resorts 🏨

[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Python-3.11+](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![LangChain](https://img.shields.io/badge/LangChain-RAG-1C3C3C?style=for-the-badge)](https://langchain.com)
[![Render](https://img.shields.io/badge/Render-000000?style=for-the-badge&logo=render&logoColor=white)](https://render.com)

**AI Concierge 24/7** là hệ thống AI Concierge kỹ thuật số đa ngôn ngữ (Việt - Anh) chuyên nghiệp và sang trọng dành cho chuỗi 6 khu nghỉ dưỡng cao cấp tại Việt Nam. Dự án được phát triển dựa trên kiến trúc backend RAG + LLM hybrid tiên tiến và tích hợp giao diện Single Page Application (SPA) cao cấp, hệ thống xác thực người dùng JWT tùy chỉnh, quản lý yêu cầu dịch vụ phòng và trang quản trị dashboard thời gian thực.

---

## 🏨 Chuỗi 6 Khu Nghỉ Dưỡng Cao Cấp
Hệ thống AI Concierge phục vụ đồng thời 6 resort hàng đầu trên cả nước:
1. **Azure Bay Resort & Spa (Đà Nẵng)** — Sang trọng hiện đại bên bờ biển.
2. **Hội An Pearl Resort (Hội An)** — Di sản văn hóa cổ kính bên sông Thu Bồn.
3. **Phú Quốc Paradise (Phú Quốc)** — Thiên đường nhiệt đới & hoàng hôn vàng rực rỡ.
4. **Sapa Highland Lodge (Sapa)** — Nét đẹp văn hóa bản địa sương mờ vùng cao.
5. **Nha Trang Coral Bay (Nha Trang)** — Trải nghiệm phiêu lưu đại dương & thể thao nước đầy năng động.
6. **Đà Lạt Pine Valley (Đà Lạt)** — Thung lũng thông mộng mơ & kiến trúc Pháp cổ điển.

---

## ✨ Điểm Nhấn Công Nghệ & Tính Năng Nổi Bật

### 🌐 Trải Nghiệm Khách Hàng (Frontend SPA)
- **Giao diện Đậm Chất Luxury**: Thiết kế theo phong cách tối giản, sang trọng với tone màu xanh Navy hoàng gia (`#0a1628`) kết hợp màu Vàng Gold tinh tế (`#c9a84c`), hiệu ứng làm mờ kính cường lực (Glassmorphism), và hiệu ứng chuyển động mượt mà.
- **Xác thực Bảo mật JWT**: Trang Đăng ký / Đăng nhập chuyên nghiệp. Tự động mã hóa mật khẩu bằng thuật toán Salted SHA-256 an toàn không phụ thuộc thư viện ngoài.
- **AI Trò chuyện Song Ngữ 24/7**: Trợ lý AI Butler phản hồi siêu tốc bằng ngôn ngữ của khách, hiển thị **Độ Tin Cậy của AI (AI Confidence Score)** để đảm bảo tính minh bạch.
- **Đặt Dịch Vụ Concierge**: Khách lưu trú có thể gửi yêu cầu xin thêm đồ dùng (khăn tắm, nước uống), đặt dịch vụ dọn phòng, giặt là, spa, đưa đón sân bay trực tiếp qua form hoặc chatbot.
- **Trang Quản Trị (Admin Dashboard)**: Dành cho Quản trị viên và nhân viên Khách sạn theo dõi số lượng người dùng, phân quyền vai trò (Admin, Staff, Guest) và cập nhật trạng thái yêu cầu dịch vụ (Chờ xử lý, Đang thực hiện, Hoàn thành, Đã hủy) thời gian thực.

### 🧠 Kiến Trúc Backend & RAG Mạnh Mẽ
- **Hybrid RAG Pipeline 3 Giai Đoạn**: Kết hợp tìm kiếm từ khóa BM25 + tìm kiếm vector dày (dense vectors), trộn kết quả qua RRF (Reciprocal Rank Fusion) và định hạng lại bằng Cross-Encoder (Reranker) cho kết quả chính xác tuyệt đối.
- **Kiểm soát Ảo giác 3 Cấp Độ**: Đánh giá câu trả lời của LLM qua 3 cấp: heuristics nhanh, mô hình NLI kiểm định tuyên bố (NLI claim verification) và LLM-as-Judge tự động chấm điểm để loại bỏ hoàn toàn các thông tin ảo giác trước khi trả về cho khách.
- **Điều phối 2 Tác nhân & Phân loại Siêu rẻ**: Bộ phân loại chitchat nhanh giúp bỏ qua Planner LLM với các câu hỏi xã giao thông thường, tiết kiệm 50-70% chi phí vận hành.
- **Bảo vệ bằng Guardrails**: Ngăn chặn tấn công Prompt Injection, tự động ẩn thông tin nhạy cảm (PII Redaction) như email, số điện thoại, số thẻ tín dụng, và kiểm soát ranh giới chủ đề (Topic Boundary).
- **Bộ nhớ Hội thoại DB-Backed**: Lưu lịch sử chat an toàn vào database, tự động tóm tắt (conversation summarization) khi đạt 12 tin nhắn để tối ưu token.

---

## 📁 Cấu Trúc Thư Mục Dự Án
```
├── app/                  # FastAPI Backend Application
│   ├── api/              # API Route Controllers (auth, services, admin)
│   ├── auth/             # JWT, API Key Authentication, & Role Helpers
│   ├── core/             # AI Orchestrator, Tools Registry, Memory Store
│   ├── database/         # Database Manager, migrations & schema DDL
│   ├── monitoring/       # Observability (Prometheus, MLflow, Logs)
│   ├── rag/              # Advanced Hybrid RAG Engine
│   └── validation/       # Hallucination Detectors & Guards
├── data/
│   └── knowledge/        # Resort Knowledge Base (Bilingual FAQs, Amenities, Policies)
├── frontend/             # Single Page Application Files
│   ├── css/              # Style sheets (Dark Luxury Design System)
│   ├── js/               # Javascript Modules (auth, chat, services, admin)
│   └── index.html        # Main SPA HTML structure
├── prompts/              # YAML Prompt templates for Planner, Executor, Summarization
├── render.yaml           # Render.com Blueprint Deployment configuration
├── Dockerfile            # Containerization configuration
└── requirements.txt      # Python dependencies
```

---

## 🚀 Hướng Dẫn Cài Đặt & Chạy Dưới Local

### 1. Yêu Cầu Hệ Thống
- Python 3.11 trở lên.
- Một API Key của nhà cung cấp LLM (OpenAI API Key hoặc Anthropic API Key).

### 2. Thiết Lập Môi Trường
Tạo môi trường ảo và cài đặt các thư viện cần thiết:
```bash
# Tạo virtual environment
python -m venv .venv

# Kích hoạt virtual environment (Windows)
.venv\Scripts\activate

# Cài đặt thư viện
pip install -r requirements.txt
```

### 3. Cấu Hình Biến Môi Trường
Sao chép file `.env.example` thành `.env` và cập nhật thông tin:
```bash
cp .env.example .env
```
Cấu hình các thông số tối thiểu:
- `RC_OPENAI_API_KEY`: API key của OpenAI.
- `RC_JWT_SECRET`: Khóa bí mật cho JWT token (generate ngẫu nhiên từ python bằng `python -c 'import secrets; print(secrets.token_urlsafe(32))'`).
- `RC_API_KEY`: API key bảo mật cho hệ thống.

### 4. Chạy Ứng Dụng
Khởi động server FastAPI phục vụ cả Backend API và Frontend SPA:
```bash
uvicorn app.main:app --reload --port 8000
```
Truy cập ứng dụng tại địa chỉ: **[http://localhost:8000](http://localhost:8000)**.
*Tài khoản đăng ký đầu tiên trên hệ thống sẽ tự động được cấp quyền **Admin**.*

---

## ☁️ Triển Khai Lên Render.com (Production)

Dự án đã được tích hợp sẵn cấu hình Render Blueprint qua file `render.yaml`. Quy trình triển khai cực kỳ dễ dàng:

1. Đẩy mã nguồn của bạn lên một kho chứa riêng tư (Private Repository) trên GitHub.
2. Đăng nhập vào **Render.com**.
3. Chọn **Blueprints** → Click **New Blueprint Instance**.
4. Chọn repository của bạn.
5. Cập nhật các biến môi trường được yêu cầu (đặc biệt là `RC_OPENAI_API_KEY`).
6. Click **Deploy**.

Render sẽ tự động xây dựng ứng dụng, thiết lập đĩa cứng lưu trữ SQLite liên tục (Persistent Disk 1GB) để giữ an toàn cho dữ liệu khách hàng và người dùng của bạn, và cung cấp một URL bảo mật HTTPS công khai.
