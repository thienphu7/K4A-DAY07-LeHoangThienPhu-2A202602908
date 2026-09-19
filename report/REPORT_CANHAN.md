# Báo Cáo Cá Nhân — Lab 7: Embedding & Vector Store

**Họ tên:** Lê Hoàng Thiên Phú
**Mã sinh viên:** 2A202602908
**Vai trò:** Thành viên — chiến lược FixedSizeChunker và benchmark OpenAI
**Nhóm:** 2 Idiots
**Ngày:** 19/09/2026

> **Nộp 1 bản / sinh viên.** Phần nhóm (lựa chọn tài liệu, thiết kế chiến lược, bộ câu hỏi đánh giá, demo) nộp chung 1 bản trong `REPORT_NHOM.md`. Chi tiết thang điểm: `docs/SCORING.md`.

**Tổng điểm phần cá nhân: 60** = Khởi động (5) + Hướng tiếp cận (10) + Hoàn thiện code (30) + Dự đoán độ tương tự (5) + Kết quả truy xuất của tôi (10).

---

## 1. Khởi động (Warm-up) — Cá nhân (5 điểm)

### Độ tương tự Cosine (Cosine Similarity) (Bài tập 1.1)

**Độ tương tự cosine cao (High cosine similarity) nghĩa là gì?**
> Hai vector embedding có cosine similarity cao khi chúng gần cùng hướng, cho thấy hai đoạn văn biểu diễn nội dung hoặc ý nghĩa gần nhau. Giá trị càng gần 1 thì mức tương đồng ngữ nghĩa càng cao.

**Ví dụ có độ tương tự CAO:**
- Câu A: Thư viện đóng cửa lúc chín giờ tối.
- Câu B: Sau 21:00, khu đọc sách không còn phục vụ.
- Tại sao tương đồng: Hai câu dùng từ vựng khác nhau nhưng đều truyền đạt cùng một thông tin về thời điểm thư viện ngừng phục vụ.

**Ví dụ có độ tương tự THẤP:**
- Câu A: Thư viện đóng cửa lúc chín giờ tối.
- Câu B: Cây xoài cần nhiều ánh nắng để phát triển.
- Tại sao khác: Một câu nói về giờ hoạt động của thư viện, câu còn lại nói về điều kiện sinh trưởng của cây; chúng không cùng chủ đề hoặc ý định.

**Tại sao độ tương tự cosine (cosine similarity) được ưu tiên hơn khoảng cách Euclid (Euclidean distance) cho text embeddings?**
> Cosine tập trung vào góc giữa hai vector, tức hướng biểu diễn ngữ nghĩa, và ít bị ảnh hưởng bởi độ lớn vector. Khoảng cách Euclid nhạy với độ lớn nên hai embedding cùng hướng nhưng khác norm vẫn có thể bị xem là xa nhau; với vector đã chuẩn hóa thì dot product cũng chính là cosine similarity.

### Bài toán tính toán Chunking (Bài tập 1.2)

**Tài liệu 10,000 ký tự, chunk_size=500, overlap=50. Bao nhiêu chunks?**
> *Phép tính:* `ceil((10.000 - 50) / (500 - 50)) = ceil(9.950 / 450) = ceil(22,111...) = 23`.
>
> *Đáp án:* 23 chunks. Kết quả kiểm tra bằng `FixedSizeChunker` cũng trả về 23.

**Nếu độ chồng chéo (overlap) tăng lên 100, số lượng chunk thay đổi thế nào? Tại sao muốn độ chồng chéo nhiều hơn?**
> Khi overlap bằng 100, số chunk là `ceil((10.000 - 100) / (500 - 100)) = ceil(9.900 / 400) = 25`, tăng 2 chunk so với overlap 50; kết quả chạy `FixedSizeChunker` cũng là 25. Overlap lớn hơn giữ thêm ngữ cảnh ở ranh giới chunk, giúp câu hoặc điều khoản bị cắt vẫn có thể được truy xuất đầy đủ, đổi lại dữ liệu lặp, dung lượng lưu trữ và chi phí embedding/search đều tăng.

---

## 2. Hướng tiếp cận của tôi (My Approach) — Cá nhân (10 điểm)

Giải thích cách tiếp cận của bạn khi lập trình (implement) các phần chính trong gói `src`.

### Các hàm chia nhỏ (Chunking Functions)

**`SentenceChunker.chunk`** — hướng tiếp cận:
> Tôi dùng lookbehind trong regex `(?:(?<=[.!?])[ \t]+|(?<=\.)\n+)` để tách tại khoảng trắng nằm sau dấu kết câu, nhờ đó dấu `.`, `!`, `?` vẫn được giữ lại. Các câu được strip, loại phần rỗng rồi gom tối đa `max_sentences_per_chunk` câu; text rỗng trả `[]`. Cách đơn giản này chưa phân biệt được dấu chấm trong chữ viết tắt như `TS.`, `v.v.` hoặc trong số thập phân, nên các trường hợp đó có thể bị cắt sai.

**`RecursiveChunker.chunk` / `_split`** — hướng tiếp cận:
> Thuật toán thử separator theo thứ tự từ ranh giới lớn đến nhỏ; mảnh còn vượt `chunk_size` được đệ quy với các separator tiếp theo. Sau khi tách xuống, các mảnh nhỏ liền kề được gom ngược lên đến sát giới hạn để tránh tạo nhiều chunk vụn. Ba base case là text rỗng, text đã không vượt kích thước, và hết separator (hoặc separator rỗng), khi đó thuật toán fallback sang cắt cố định theo số ký tự.

### Lớp EmbeddingStore

**`add_documents` + `search`** — hướng tiếp cận:
> `add_documents` xem mỗi `Document` là một record, sao chép metadata, bổ sung `doc_id` của file gốc nếu còn thiếu và tính embedding đúng một lần cho nội dung. `search` nhúng query, dùng dot product với embedding đã chuẩn hóa của từng record, sắp xếp điểm giảm dần rồi lấy `top_k`; kết quả không trả trường `embedding` để tránh làm bẩn output.

**`search_with_filter` + `delete_document`** — hướng tiếp cận:
> `search_with_filter` lọc metadata trước khi chạy similarity search, nhờ đó các vị trí top-k không bị tài liệu sai đối tượng chiếm mất. Cả search thường và search có filter dùng chung `_search_records` để bảo đảm cách chấm điểm nhất quán. `delete_document` loại toàn bộ record/chunk có `metadata['doc_id']` khớp file gốc và trả `True` khi thực sự xóa được ít nhất một record.

### Tác tử KnowledgeBaseAgent

**`answer`** — hướng tiếp cận:
> `answer` truy xuất top-k rồi dựng từng khối ngữ cảnh dạng `[1] Source: ...`, `[2] Source: ...` để câu trả lời có thể trích dẫn và truy vết về chunk/file nguồn. Prompt yêu cầu chỉ dùng ngữ cảnh, không bổ sung dữ kiện bên ngoài và phải nói rõ khi thiếu thông tin. Nếu store không trả kết quả, agent trả thông báo “không tìm thấy” ngay và không gọi `llm_fn`.

---

## 3. Hoàn thiện code (Core Implementation) — Cá nhân (30 điểm)

Vượt qua bộ kiểm thử là điều kiện tính điểm phần này.

### Kết Quả Kiểm Thử (Test Results)

```
============================= test session starts =============================
platform win32 -- Python 3.11.16, pytest-9.1.1, pluggy-1.6.0
cachedir: .pytest_cache
rootdir: D:\VinAI\labs\K4A-DAY07-LeHoangThienPhu-2A202602908
plugins: anyio-4.15.1
collecting ... collected 42 items

tests/test_solution.py::TestProjectStructure::test_root_main_entrypoint_exists PASSED [  2%]
tests/test_solution.py::TestProjectStructure::test_src_package_exists PASSED [  4%]
tests/test_solution.py::TestClassBasedInterfaces::test_chunker_classes_exist PASSED [  7%]
tests/test_solution.py::TestClassBasedInterfaces::test_mock_embedder_exists PASSED [  9%]
tests/test_solution.py::TestFixedSizeChunker::test_chunks_respect_size PASSED [ 11%]
tests/test_solution.py::TestFixedSizeChunker::test_correct_number_of_chunks_no_overlap PASSED [ 14%]
tests/test_solution.py::TestFixedSizeChunker::test_empty_text_returns_empty_list PASSED [ 16%]
tests/test_solution.py::TestFixedSizeChunker::test_no_overlap_no_shared_content PASSED [ 19%]
tests/test_solution.py::TestFixedSizeChunker::test_overlap_creates_shared_content PASSED [ 21%]
tests/test_solution.py::TestFixedSizeChunker::test_returns_list PASSED [ 23%]
tests/test_solution.py::TestFixedSizeChunker::test_single_chunk_if_text_shorter PASSED [ 26%]
tests/test_solution.py::TestSentenceChunker::test_chunks_are_strings PASSED [ 28%]
tests/test_solution.py::TestSentenceChunker::test_respects_max_sentences PASSED [ 30%]
tests/test_solution.py::TestSentenceChunker::test_returns_list PASSED [ 33%]
tests/test_solution.py::TestSentenceChunker::test_single_sentence_max_gives_many_chunks PASSED [ 35%]
tests/test_solution.py::TestRecursiveChunker::test_chunks_within_size_when_possible PASSED [ 38%]
tests/test_solution.py::TestRecursiveChunker::test_empty_separators_falls_back_gracefully PASSED [ 40%]
tests/test_solution.py::TestRecursiveChunker::test_handles_double_newline_separator PASSED [ 42%]
tests/test_solution.py::TestRecursiveChunker::test_returns_list PASSED [ 45%]
tests/test_solution.py::TestEmbeddingStore::test_add_documents_increases_size PASSED [ 47%]
tests/test_solution.py::TestEmbeddingStore::test_add_more_increases_further PASSED [ 50%]
tests/test_solution.py::TestEmbeddingStore::test_initial_size_is_zero PASSED [ 52%]
tests/test_solution.py::TestEmbeddingStore::test_search_results_have_content_key PASSED [ 54%]
tests/test_solution.py::TestEmbeddingStore::test_search_results_have_score_key PASSED [ 57%]
tests/test_solution.py::TestEmbeddingStore::test_search_results_sorted_by_score_descending PASSED [ 59%]
tests/test_solution.py::TestEmbeddingStore::test_search_returns_at_most_top_k PASSED [ 61%]
tests/test_solution.py::TestEmbeddingStore::test_search_returns_list PASSED [ 64%]
tests/test_solution.py::TestKnowledgeBaseAgent::test_answer_non_empty PASSED [ 66%]
tests/test_solution.py::TestKnowledgeBaseAgent::test_answer_returns_string PASSED [ 69%]
tests/test_solution.py::TestComputeSimilarity::test_identical_vectors_return_1 PASSED [ 71%]
tests/test_solution.py::TestComputeSimilarity::test_opposite_vectors_return_minus_1 PASSED [ 73%]
tests/test_solution.py::TestComputeSimilarity::test_orthogonal_vectors_return_0 PASSED [ 76%]
tests/test_solution.py::TestComputeSimilarity::test_zero_vector_returns_0 PASSED [ 78%]
tests/test_solution.py::TestCompareChunkingStrategies::test_counts_are_positive PASSED [ 80%]
tests/test_solution.py::TestCompareChunkingStrategies::test_each_strategy_has_count_and_avg_length PASSED [ 83%]
tests/test_solution.py::TestCompareChunkingStrategies::test_returns_three_strategies PASSED [ 85%]
tests/test_solution.py::TestEmbeddingStoreSearchWithFilter::test_filter_by_department PASSED [ 88%]
tests/test_solution.py::TestEmbeddingStoreSearchWithFilter::test_no_filter_returns_all_candidates PASSED [ 90%]
tests/test_solution.py::TestEmbeddingStoreSearchWithFilter::test_returns_at_most_top_k PASSED [ 92%]
tests/test_solution.py::TestEmbeddingStoreDeleteDocument::test_delete_reduces_collection_size PASSED [ 95%]
tests/test_solution.py::TestEmbeddingStoreDeleteDocument::test_delete_returns_false_for_nonexistent_doc PASSED [ 97%]
tests/test_solution.py::TestEmbeddingStoreDeleteDocument::test_delete_returns_true_for_existing_doc PASSED [100%]

============================= 42 passed in 0.15s ==============================
```

**Số lượng bài test vượt qua (pass):** 42 / 42

---

## 4. Dự đoán độ tương tự (Similarity Predictions) — Cá nhân (5 điểm)

| Cặp | Câu A | Câu B | Dự đoán | Điểm thực tế | Đúng? |
|------|-----------|-----------|---------|--------------|-------|
| 1 | The library closes at nine in the evening. | After 9:00 PM, the reading area is no longer open. | Cao | 0,6615 | Có |
| 2 | The library closes at nine in the evening. | Mango trees need plenty of sunlight to grow. | Thấp | 0,1036 | Có |
| 3 | Students may borrow Short Loan items. | Students may not borrow Short Loan items. | Thấp | 0,9151 | Không |
| 4 | Return the borrowed book to the original library location. | Bring the Short Loan item back to where it was borrowed. | Cao | 0,6212 | Có |
| 5 | Sinh viên cao học được sử dụng dịch vụ chia sẻ tài nguyên. | Postgraduate students are eligible for Resource Sharing. | Cao | 0,4008 | Không (chỉ ở mức trung bình) |

**Kết quả nào bất ngờ nhất? Điều này nói gì về cách embeddings biểu diễn ý nghĩa?**
> Cặp 3 bất ngờ nhất: chỉ thêm từ phủ định `not` nhưng cosine vẫn đạt 0,9151 vì hai câu chia sẻ gần như toàn bộ từ vựng và chủ đề, dù ý nghĩa chính sách đối lập. Cặp Việt–Anh cùng nghĩa chỉ đạt 0,4008, cho thấy embedding có tín hiệu đa ngữ nhưng mức tương đồng còn phụ thuộc ngôn ngữ và cách diễn đạt. Vì vậy cosine cao không tự bảo đảm hai câu có cùng lập trường hoặc cùng đáp án.

> Điểm thực tế được đo bằng `text-embedding-3-small`; quy ước dự đoán nhị phân trong bảng là từ 0,5 trở lên được xem là cao.

---

## 5. Kết quả truy xuất của tôi (Competition Results) — Cá nhân (10 điểm)

Chạy **5 câu hỏi đánh giá của nhóm** trên mã nguồn cá nhân của bạn trong gói `src`. **5 câu hỏi này phải trùng với các thành viên cùng nhóm** (xem `REPORT_NHOM.md`).

| # | Câu hỏi (Query) | Top-1 Chunk truy xuất được (tóm tắt) | Điểm Score | Có liên quan không? (Relevant) | Câu trả lời của Agent (tóm tắt) |
|---|-------|--------------------------------|-------|-----------|------------------------|
| 1 | How many Short Loan items may be borrowed at once, and how long does each loan last? | `borrowing-limits#0` — giới hạn Standard/Short Loan | 0,7756 | Có, đúng chunk ở top-1 (2/2) | Tối đa 2 món Short Loan cùng lúc, mỗi món được mượn 3 giờ, trích dẫn `[1]`. |
| 2 | Under what conditions may a General Collection item be kept for up to 365 days? | `borrowing-terms#0` — điều kiện của General Collection | 0,5479 | Có, đúng chunk ở top-1 (2/2) | Không có recall; enrolment/membership còn hiệu lực; hồ sơ không có fines hoặc blocks, trích dẫn `[1]`. |
| 3 | How do I request a digital copy of a journal article or book chapter? | `resource-sharing-staff#1` — quy trình Resource Sharing của staff | 0,4827 | Top-1 chưa trực tiếp; chunk trả lời `requesting-items#2` ở top-2 (1/2) | Đăng nhập catalogue, chọn journal/location, chọn “Request a digital copy”, hoàn tất form và copyright acknowledgement rồi gửi, trích dẫn `[2]`. |
| 4 | Where must a Short Loan item be returned? | `borrowing-limits#0` — giới hạn mượn, chưa chứa nơi trả | 0,5508 | Top-1 chưa trả lời; chunk đúng `returning-items#0` ở top-2 (1/2) | Trả Short Loan về đúng địa điểm đã mượn, trích dẫn `[2]`. |
| 5 | How many items can I borrow through Resource Sharing in a calendar year, and who is eligible? | `resource-sharing-students#0` — Eligibility and allowance | 0,6819 | Có, đúng chunk ở top-1 sau filter `audience=student` (2/2) | Postgraduate và honours students đủ điều kiện; tối đa 100 items mỗi năm dương lịch, trích dẫn `[1]`. |

**Bao nhiêu câu hỏi trả về chunk có liên quan trong top-3?** 5 / 5; tổng điểm theo thứ hạng nội dung là **8/10**.

**Backend và phân tích lỗi:**
> Benchmark dùng `text-embedding-3-small` với cache SHA-256, chiến lược cá nhân `FixedSizeChunker(chunk_size=500, overlap=50)`, tạo 16 chunk từ 6 tài liệu. Q3 và Q4 là hai failure case thực: tài liệu/chunk cùng chủ đề đứng top-1 nhưng không chứa trực tiếp đáp án; chunk trả lời chỉ đứng top-2. Nguyên nhân là cosine ưu tiên mức giống chủ đề chứ không đo “mật độ đáp án”. Có thể cải thiện bằng ranh giới section/heading, metadata `category`, reranker tập trung vào khả năng trả lời, hoặc overlap có chọn lọc.

**A/B metadata filter ở câu 5:**
> Có filter, top-3 đều thuộc `resource-sharing-students`; không filter, chunk staff chen vào vị trí 2. Chunk đáp án student vẫn đứng top-1 ở cả hai lượt với OpenAI embedding, nhưng filter loại bỏ ngữ cảnh sai đối tượng và giảm nguy cơ agent trộn điều kiện student/staff. Top-3 thay đổi nên phép A/B cho thấy precision theo đối tượng được cải thiện.

**Điều hay nhất tôi học được từ thành viên khác / nhóm khác (qua demo):**
> Từ chiến lược HeadingChunker của anh Đinh Văn Hùng, tôi học được rằng heading là tín hiệu cấu trúc quan trọng đối với văn bản quy định và cần được gắn lại vào mọi mảnh con khi section quá dài. Tuy nhiên việc tách section đẹp chưa đủ: cần chấm ở mức nội dung, vì đúng `doc_id` nhưng sai section vẫn không giúp agent trả lời.

---

## Tự Đánh Giá (Phần Cá Nhân)

| Tiêu chí | Điểm tự đánh giá |
|----------|-------------------|
| Khởi động (Warm-up) | 5 / 5 |
| Hướng tiếp cận của tôi (My Approach) | 10 / 10 |
| Hoàn thiện code (Core Implementation — tests) | 30 / 30 |
| Dự đoán độ tương tự (Similarity Predictions) | 5 / 5 |
| Kết quả truy xuất của tôi (Competition Results) | 8 / 10 |
| **Tổng phần cá nhân** | **58 / 60** |
