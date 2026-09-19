# Báo Cáo Nhóm — Lab 7: Embedding & Vector Store

**Nhóm:** 2 Idiots

**Thành viên:**
- Đinh Văn Hùng — 2A202602443 — Nhóm trưởng; R2 Benchmark; R3 Strategy
- Lê Hoàng Thiên Phú — 2A202602908 — chiến lược FixedSizeChunker; benchmark OpenAI

**Ngày:** 19/09/2026

> **Nộp 1 bản / nhóm.** Phần cá nhân (hướng tiếp cận, kết quả riêng, dự đoán…) mỗi thành viên nộp riêng trong `REPORT_CANHAN.md`. Chi tiết thang điểm: `docs/SCORING.md`.

**Tổng điểm phần nhóm: 40** = Lựa chọn tài liệu (10) + Thiết kế chiến lược (15) + Chất lượng truy xuất (10) + Thuyết trình (5).

---

## 1. Lựa chọn tài liệu (Document Set Quality) — Nhóm (10 điểm)

### Chủ đề (Domain) & Lý Do Chọn

**Chủ đề:** Quy định mượn và yêu cầu tài liệu của Thư viện University of Sydney (K4-L3A).

**Tại sao nhóm chọn chủ đề này?**
> Đây là nhóm quy định đại học công khai, có nhiều điều kiện, con số và mốc thời gian phù hợp để kiểm tra chất lượng retrieval. Nguồn chính thức cũng phân biệt người học và nhân viên trong dịch vụ Resource Sharing, nhờ đó trường `audience` tạo ra phép thử metadata filter có ý nghĩa thay vì chỉ tồn tại trên schema.

### Danh sách tài liệu (Data Inventory)

| # | Tên tài liệu | Nguồn (Source URL) | Ngày lấy / Phiên bản | Số ký tự | Metadata đã gán |
|---|--------------|------------|--------------------|----------|-----------------|
| 1 | Limits on borrowing | [University of Sydney Library](https://www.library.sydney.edu.au/support/borrowing/limits-on-borrowing) | 2026-09-19 / `not-stated` | 960 | `audience=all`, `category=borrowing-limits`, `department=library`, `language=en` |
| 2 | Borrowing terms and conditions | [University of Sydney Library](https://www.library.sydney.edu.au/about/governance/borrowing-terms-and-conditions) | 2026-09-19 / `not-stated` | 1.400 | `audience=all`, `category=borrowing-policy`, `department=library`, `language=en` |
| 3 | Requesting items | [University of Sydney Library](https://www.library.sydney.edu.au/support/borrowing/requesting-items) | 2026-09-19 / `not-stated` | 1.575 | `audience=all`, `category=requests`, `department=library`, `language=en` |
| 4 | Returning items | [University of Sydney Library](https://www.library.sydney.edu.au/support/borrowing/returning-items) | 2026-09-19 / `not-stated` | 1.195 | `audience=all`, `category=returns`, `department=library`, `language=en` |
| 5 | Resource sharing for eligible students | [University of Sydney Library](https://www.library.sydney.edu.au/support/borrowing/request-an-item-from-outside-our-library) | 2026-09-19 / `not-stated` | 1.404 | `audience=student`, `category=resource-sharing`, `department=library`, `language=en` |
| 6 | Resource sharing for staff | [University of Sydney Library](https://www.library.sydney.edu.au/support/borrowing/request-an-item-from-outside-our-library) | 2026-09-19 / `not-stated` | 1.291 | `audience=staff`, `category=resource-sharing`, `department=library`, `language=en` |

Corpus có **6 tài liệu**, nằm trong yêu cầu 5–10 tài liệu của lab. `sources.csv` có đủ 6 `doc_id` tương ứng và metadata của mỗi file được trải xuống mọi chunk khi nạp benchmark.

**Danh sách kiểm tra quản trị dữ liệu (Data governance checklist):**
- [x] Tập tài liệu chỉ chứa nguồn công khai/được phép dùng và không chứa dữ liệu cá nhân, thông tin đăng nhập hoặc tài liệu nội bộ.
- [x] Mỗi tài liệu có `source_url`, `retrieved_at`, `document_version` và `audience` trong metadata.
- [x] `doc_id` trong metadata trỏ về file gốc; `Document.id` có dạng `file#chunk_index`.

### Cấu trúc Metadata (Metadata Schema)

| Trường metadata | Kiểu | Ví dụ giá trị | Tại sao hữu ích cho truy xuất? |
|----------------|------|---------------|-------------------------------|
| `doc_id` | string | `resource-sharing-students` | Liên kết file nguồn, chunk và dòng trong `sources.csv`; hỗ trợ xóa toàn bộ chunk của một tài liệu. |
| `title` | string | `Resource sharing for eligible students` | Bổ sung tín hiệu ngữ nghĩa và giúp hiển thị nguồn dễ đọc. |
| `source_url` | URL string | `https://www.library.sydney.edu.au/...` | Cho phép truy vết và kiểm chứng câu trả lời ở nguồn chính thức. |
| `retrieved_at` | date (`YYYY-MM-DD`) | `2026-09-19` | Cho biết thời điểm chụp dữ liệu khi quy định có thể thay đổi. |
| `document_version` | string | `not-stated` | Lưu phiên bản khi nguồn công bố; không tự suy đoán phiên bản. |
| `audience` | enum string | `student`, `staff`, `all` | Lọc đúng đối tượng, đặc biệt tách hai quy định Resource Sharing gần giống nhau. |
| `department` | string | `library` | Thu hẹp retrieval theo đơn vị khi corpus được mở rộng. |
| `category` | string | `returns`, `requests`, `resource-sharing` | Thu hẹp theo loại quy định hoặc thao tác cần tra cứu. |
| `language` | string | `en` | Hỗ trợ lựa chọn embedder và lọc ngôn ngữ cho corpus đa ngữ. |

---

## 2. Thiết kế chiến lược (Strategy Design) — Nhóm (15 điểm)

### Phân tích đường cơ sở (Baseline Analysis)

Frontmatter YAML được bỏ trước khi chạy `ChunkingStrategyComparator().compare()`:

| Tài liệu | Chiến lược | Số chunk | Độ dài trung bình | Nhận xét về ngữ cảnh |
|-----------|------------|----------|---------------------|----------------------|
| `borrowing-limits.md` | FixedSize (`fixed_size`) | 2 | 343,0 | Ít chunk nhưng có thể cắt giữa mục. |
| `borrowing-limits.md` | Sentence (`by_sentences`) | 3 | 227,0 | Giữ ranh giới câu, chi tiết hơn. |
| `borrowing-limits.md` | Recursive (`recursive`) | 2 | 342,0 | Giữ được các đoạn lớn. |
| `borrowing-terms.md` | FixedSize (`fixed_size`) | 3 | 368,7 | Có thể trộn hai mục ở ranh giới. |
| `borrowing-terms.md` | Sentence (`by_sentences`) | 4 | 274,8 | Mạch lạc theo câu nhưng nhiều chunk hơn. |
| `borrowing-terms.md` | Recursive (`recursive`) | 3 | 367,3 | Cân bằng kích thước và ngữ cảnh. |
| `requesting-items.md` | FixedSize (`fixed_size`) | 3 | 438,3 | Có nguy cơ cắt giữa một quy trình. |
| `requesting-items.md` | Sentence (`by_sentences`) | 4 | 327,0 | Mạch lạc nhưng tăng số record. |
| `requesting-items.md` | Recursive (`recursive`) | 4 | 327,2 | Phù hợp tài liệu có nhiều đoạn/mục. |

Trên toàn bộ 6 tài liệu với cấu hình benchmark chung: FixedSize tạo 16 chunk (trung bình 412,8 ký tự), Sentence 21 (289,0), Recursive 18 (337,8), và Heading 25 (245,0).

### Chiến lược của từng thành viên

**Thành viên 1 — Đinh Văn Hùng (R2 Benchmark + R3 Strategy)**
- **Loại chiến lược:** Custom `HeadingChunker`.
- **Mô tả & lý do chọn:** Tách trước mỗi heading `##` vì mỗi mục quy định là một đơn vị ngữ nghĩa do người biên soạn xác định. Section dài hơn 500 ký tự được hạ xuống `RecursiveChunker`, đồng thời gắn lại heading vào từng mảnh con để các mảnh sau không mất chủ đề.
- **Nguồn triển khai:** [Repository của Đinh Văn Hùng](https://github.com/hungdinh82/K4-DAY07-DinhVanHung-2A202602443), file `bench.py`.

```python
for piece in self._recursive.chunk(body):
    chunks.append(f"{heading}\n{piece}".strip() if heading else piece)
```

**Thành viên 2 — Lê Hoàng Thiên Phú**
- **Loại chiến lược:** `FixedSizeChunker(chunk_size=500, overlap=50)`.
- **Mô tả & lý do chọn:** Đây là baseline dễ kiểm soát, tạo ít record và dùng overlap để giảm mất ngữ cảnh ở ranh giới 500 ký tự. Nhược điểm là ranh giới cắt không hiểu cấu trúc heading và đôi khi trộn nội dung của hai mục.

```python
PERSONAL_CHUNKER = FixedSizeChunker(chunk_size=500, overlap=50)
```

### So Sánh Giữa Các Thành Viên

Để so sánh công bằng, nhóm chạy lại cả hai chiến lược với cùng corpus, 5 query, `top_k=3`, gold marker và backend `text-embedding-3-small`. Lượt chạy gốc của Hùng dùng MockEmbedder đạt 3/10 và chỉ được giữ làm đối chứng, vì điểm MD5 không có ý nghĩa ngữ nghĩa.

| Thành viên | Chiến lược | Điểm nội dung (/10) | Điểm mạnh | Điểm yếu |
|-----------|------------|---------------------|-----------|----------|
| Lê Hoàng Thiên Phú | FixedSize 500, overlap 50 | **8/10** | Ít chunk (16), overlap giữ ngữ cảnh; 5/5 câu có đáp án trong top-3. | Q3 và Q4: chunk đáp án chỉ đứng top-2; chunk lớn có thể trộn nhiều mục. |
| Đinh Văn Hùng | HeadingChunker 500 + recursive fallback | **7/10 theo gold marker** | Section rõ nghĩa, giữ heading, Q1/Q2/Q5 đứng top-1. | Tạo 25 chunk; Q3 ở top-2 và gold marker của Q4 không khớp dù top-1 có cụm đồng nghĩa “same location”. |

**Chiến lược nào tốt nhất cho chủ đề này? Tại sao?**
> Theo thang chấm tự động bằng gold marker, FixedSize tốt hơn một điểm (8/10 so với 7/10) và tiết kiệm record hơn. Tuy nhiên HeadingChunker tạo các section dễ đọc, dễ truy vết hơn; trường hợp Q4 còn cho thấy exact-string marker có thể đánh giá thấp một chunk đúng về ngữ nghĩa. Với corpus quy định, phương án tốt nhất trong lần cải tiến tiếp theo là heading-aware chunking kết hợp overlap nhỏ/reranker, thay vì chỉ tối ưu một chỉ số.

---

## 3. Câu hỏi đánh giá & Chất lượng truy xuất (Retrieval Quality) — Nhóm (10 điểm)

### Câu hỏi đánh giá & Câu trả lời chuẩn

| # | Câu hỏi (Query) | Câu trả lời chuẩn (Gold Answer) | Chunk chứa thông tin |
|---|-----------------|---------------------------------|----------------------|
| 1 | How many Short Loan items may be borrowed at once, and how long does each loan last? | Only two Short Loan items may be borrowed at once; each lasts 3 hours. | `borrowing-limits`, mục Standard limits |
| 2 | Under what conditions may a General Collection item be kept for up to 365 days? | No recall; enrolment or membership remains current; no fines or blocks. | `borrowing-terms`, mục General Collection loans |
| 3 | How do I request a digital copy of a journal article or book chapter? | Sign in, select journal/location, choose Request a digital copy, complete the form and copyright acknowledgement, then submit. | `requesting-items`, mục Collection and digitisation |
| 4 | Where must a Short Loan item be returned? | To the location from which it was borrowed. | `returning-items`, mục Return chutes |
| 5 | How many items can I borrow through Resource Sharing in a calendar year, and who is eligible? | Postgraduate and honours students are eligible; they may borrow up to 100 items per calendar year. | `resource-sharing-students`, mục Eligibility and allowance; filter `audience=student` |

### Tổng hợp chất lượng truy xuất của nhóm

| # | Chiến lược tốt nhất cho câu này | Chunk liên quan trong top-3? | Kết quả và ghi chú |
|---|---------------------------------|-------------------------------|--------------------|
| 1 | Recursive / FixedSize / Heading | Có | Cả ba đưa đáp án lên top-1; Recursive có score cao nhất 0,7881. |
| 2 | HeadingChunker | Có | Đúng section ở top-1, score 0,6332. |
| 3 | Sentence hoặc Recursive | Có | Đúng section ở top-1, score 0,6880; FixedSize/Heading để ở top-2. |
| 4 | SentenceChunker | Có | Đúng chunk ở top-1, score 0,7309; FixedSize ở top-2. Heading top-1 có cách diễn đạt đồng nghĩa nhưng không khớp gold marker. |
| 5 | Sentence / Recursive / FixedSize / Heading + filter | Có | Cả bốn có chunk student ở top-1; Sentence cao nhất 0,6947. |

**Lọc bằng metadata có giúp ích không? Ở câu hỏi nào?**
> Có, ở câu 5. Với `audience=student`, cả ba vị trí đều là chunk của tài liệu student; không filter, chunk `resource-sharing-staff` chen vào top-2 hoặc top-3 ở cả bốn chiến lược. Với OpenAI embedding, chunk student vẫn đứng top-1 ngay cả khi không lọc, nên filter không đổi content rank nhưng cải thiện precision theo đối tượng và ngăn agent trộn quy định staff/student.

### A/B câu 5 trên bốn chiến lược

| Chiến lược | Có filter | Không filter | Kết luận |
|------------|-----------|--------------|----------|
| FixedSize | top-1 student; top-3 đều student | top-1 student, top-2 staff | Filter loại ngữ cảnh staff. |
| Sentence | top-1 student; top-3 đều student | top-1 student, top-2 staff | Filter cải thiện độ thuần của context. |
| Recursive | top-1 student; top-3 đều student | top-1 student, top-2 staff | Filter giảm nguy cơ trộn đối tượng. |
| Heading | top-1 eligibility student; top-3 đều student | top-1 student, top-3 staff | Filter loại section eligibility của staff. |

### Failure case và đề xuất sửa

> **Failure case chính — Q3 với FixedSize:** top-1 là `resource-sharing-staff#1` (score 0,4827), cùng chủ đề “request/digital copy” nhưng không chứa đầy đủ quy trình gold; chunk đúng `requesting-items#2` chỉ đứng top-2 (0,4635). Cosine đang đo độ gần chủ đề, không đo mức đầy đủ của đáp án. Đề xuất thêm metadata `category=requests`, dùng reranker theo câu hỏi–đáp án, hoặc ưu tiên section “Collection and digitisation”.

> **Failure case đánh giá — Q4 với Heading:** exact gold marker báo 0 vì chunk top-1 viết “returned to the same location” thay vì nguyên cụm “location from which it was borrowed”. Đây là false negative của phép chấm chuỗi, không hẳn là lỗi retrieval. Nên khai báo nhiều marker đồng nghĩa hoặc kiểm tra ngữ nghĩa thủ công bên cạnh điểm tự động.

---

## 4. Thuyết trình (Demo) & Bài học nhóm — Nhóm (5 điểm)

**Những phân tích hay nhất nhóm sẽ trình bày:**
> - Đúng `doc_id` chưa đủ; cần kiểm tra đúng section và câu chứa đáp án trong top-3.
> - Cùng OpenAI embedding, thay chunking làm thay đổi rõ Q3/Q4: Sentence thắng ở quy trình và nơi trả, Heading mạnh ở các section điều kiện.
> - Metadata `audience` không nhất thiết đổi top-1 nhưng làm top-3 sạch hơn, giúp agent không trộn quy định student và staff.

**Bài học rút ra khi so sánh trong nhóm:**
> FixedSize tạo ít record và đạt điểm marker cao hơn một chút, nhưng chunk có thể chứa nhiều ý. Heading tạo section mạch lạc và truy vết tốt hơn nhưng tăng số chunk, trong khi Sentence phù hợp nhất cho những câu hỏi nhắm tới một bước/quy định ngắn. Chất lượng retrieval là kết quả kết hợp của ranh giới chunk, embedding, metadata và cách chấm—not chỉ của một tham số.

**Nếu làm lại, nhóm sẽ thay đổi gì trong chiến lược dữ liệu?**
> Nhóm sẽ dùng một hybrid chunker: tách theo heading trước, recursive khi section dài, thêm overlap nhỏ tại ranh giới và giữ heading trong mọi chunk con. Gold marker sẽ hỗ trợ các cách diễn đạt tương đương; sau dense retrieval sẽ có reranker hoặc kiểm tra khả năng trả lời để tránh chunk đúng chủ đề nhưng thiếu dữ kiện.

---

## Tự Đánh Giá (Phần Nhóm)

| Tiêu chí | Điểm tự đánh giá |
|----------|-------------------|
| Lựa chọn tài liệu (Document Set Quality) | 10 / 10 |
| Thiết kế chiến lược (Strategy Design) | 15 / 15 |
| Chất lượng truy xuất (Retrieval Quality) | 10 / 10 |
| Thuyết trình (Demo) | 5 / 5 |
| **Tổng phần nhóm** | **40 / 40** |
