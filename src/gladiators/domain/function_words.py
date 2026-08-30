"""W16-R3 — từ chức năng là một REGISTRY, không phải ba set cục bộ.

Trước module này có ít nhất ba bản rời rạc của cùng khái niệm:

* ``value_probe.named_but_absent`` giữ một set ``stop`` viết tay;
* ``synthesizer._LITERAL_QUALIFIER_MARKERS`` giữ một tuple khác;
* ``semantic_parser`` rải các tuple ad-hoc trong thân hàm.

Ba bản trùng nhau hôm nay là **ngẫu nhiên, không phải bất biến** — và repo này
đã có tiền lệ hai danh sách của cùng một luật lệch nhau (hai bộ khớp alias song
song, `AliasIndex.find_in` và `DeterministicSemanticParser._link`).

**Vì sao registry này quan trọng hơn vẻ ngoài của nó.** ``BindingLedger`` phân
loại phần dư bằng một hàm TOÀN PHẦN: token không được claim và không phải từ
chức năng sẽ rơi vào ``unknown_concept``, và W22 biến ``unknown_concept`` thành
một câu hỏi lại. Nên **một từ nối thiếu ở đây là một câu bị từ chối oan.** Đó
chính là rủi ro mà nghiệm thu W22 khoá bằng điều kiện *"``over_refusal_rate``
không được tăng"*.
"""
from __future__ import annotations

from functools import lru_cache

# Đã fold (bỏ dấu, lowercase) — cùng dạng với ``spans.fold``.
FUNCTION_WORDS: dict[str, frozenset[str]] = {
    "vi": frozenset({
        # giới từ, liên từ, hạn định
        "cua", "tai", "o", "trong", "ngoai", "tren", "duoi", "giua", "voi", "va",
        "hay", "hoac", "thi", "la", "co", "khong", "cho", "den", "tu", "theo",
        "ve", "boi", "do", "nen", "ma", "cac", "nhung", "moi", "mot", "nhung",
        "nay", "kia", "do", "ay", "duoc", "bi", "se", "dang", "da", "roi",
        "cung", "van", "chi", "ca", "toan", "bo", "tat", "nhu", "the", "nao",
        # hỏi/đại từ đã được frame grammar tiêu thụ; giữ ở đây làm lưới an toàn
        "gi", "sao", "vay", "a", "u", "nhi", "ha",
        # lễ độ / rác hội thoại
        "xin", "vui", "long", "giup", "toi", "minh", "ban", "em", "anh", "chi",
        "hay", "cho", "biet", "hoi", "muon", "can", "tim", "xem", "tra", "loi",
    }),
    "id": frozenset({
        "di", "ke", "dari", "untuk", "dengan", "pada", "dalam", "atas", "bawah",
        "dan", "atau", "yang", "itu", "ini", "adalah", "ada", "tidak", "bukan",
        "akan", "sudah", "sedang", "juga", "saja", "semua", "para", "sebuah",
        "apa", "bagaimana", "tolong", "saya", "kamu", "anda", "mohon", "bisa",
    }),
    "en": frozenset({
        "the", "a", "an", "of", "in", "on", "at", "for", "with", "by", "from",
        "to", "and", "or", "but", "is", "are", "was", "were", "be", "been",
        "has", "have", "had", "do", "does", "did", "will", "would", "can",
        "could", "should", "there", "their", "its", "it", "this", "that",
        "these", "those", "all", "any", "some", "each", "please", "show",
        "tell", "me", "us", "i", "you", "we", "give", "list", "get",
    }),
}

# Tên thị trường: chúng LÀ nội dung, nhưng country binder đã claim chúng trước.
# Giữ ở đây làm lưới an toàn cho câu mà country binder không bắt (viết tắt lạ),
# để một tên nước còn dư không bị chấm là ``unknown_concept``.
MARKET_WORDS = frozenset({
    "vn", "id", "viet", "nam", "vietnam", "indonesia", "indo", "vietnamese",
})


@lru_cache(maxsize=1)
def _all_function_words() -> frozenset[str]:
    words: set[str] = set(MARKET_WORDS)
    for group in FUNCTION_WORDS.values():
        words |= group
    return frozenset(words)


def is_function_word(normalized: str, language: str | None = None) -> bool:
    """Token này bỏ qua được khi đi tìm nội dung?

    ``language`` chỉ thu hẹp; bỏ trống thì tra hợp của cả ba. Tra hợp là lựa
    chọn CÓ CHỦ ĐÍCH: câu hỏi thật trộn ngôn ngữ (``"berapa listing tại VN"``),
    và một từ nối tiếng Indonesia trong câu tiếng Việt vẫn là một từ nối.
    """
    if not normalized:
        return True
    if language and language in FUNCTION_WORDS:
        return normalized in FUNCTION_WORDS[language] or normalized in MARKET_WORDS
    return normalized in _all_function_words()


def function_words(language: str | None = None) -> frozenset[str]:
    if language and language in FUNCTION_WORDS:
        return FUNCTION_WORDS[language] | MARKET_WORDS
    return _all_function_words()
