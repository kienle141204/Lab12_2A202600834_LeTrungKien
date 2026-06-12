"""
Economics LLM — OpenAI gpt-4o-mini
Chatbot hỏi đáp về kinh tế học, hỗ trợ tiếng Việt và tiếng Anh.
"""
import os
from openai import OpenAI

SYSTEM_PROMPT = """Bạn là chuyên gia kinh tế học với 20 năm kinh nghiệm giảng dạy và nghiên cứu.
Bạn có thể trả lời bằng tiếng Việt hoặc tiếng Anh tùy theo ngôn ngữ của câu hỏi.

Chuyên môn của bạn bao gồm:
- Kinh tế vi mô: cung cầu, thị trường, giá cả, độ co giãn
- Kinh tế vĩ mô: GDP, lạm phát, thất nghiệp, tăng trưởng kinh tế
- Chính sách tiền tệ và tài khóa
- Kinh tế quốc tế: thương mại, tỷ giá hối đoái
- Thị trường tài chính: chứng khoán, trái phiếu, tiền điện tử
- Kinh tế Việt Nam và ASEAN

Hãy trả lời rõ ràng, dễ hiểu, với ví dụ thực tế khi phù hợp.
Nếu câu hỏi không liên quan đến kinh tế, hãy lịch sự từ chối và hướng dẫn về chủ đề kinh tế."""


def ask(question: str, history: list[dict] | None = None) -> str:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": question})

    response = client.chat.completions.create(
        model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
        messages=messages,
        max_tokens=1024,
        temperature=0.7,
    )
    return response.choices[0].message.content


def ask_stream(question: str, history: list[dict] | None = None):
    """Yield text chunks for streaming."""
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": question})

    stream = client.chat.completions.create(
        model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
        messages=messages,
        max_tokens=1024,
        temperature=0.7,
        stream=True,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta
