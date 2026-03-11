# T031a：MinerU 可选依赖封装应可导入，并在未安装时给出明确错误
import pytest


def test_parse_bytes_without_mineru_raises():
    from parsing.service import parse_document_bytes
    from parsing.errors import MinerUNotAvailable, ParsingError

    # 随便给一点 bytes；在未安装 MinerU 环境应抛 MinerUNotAvailable
    with pytest.raises((MinerUNotAvailable, ParsingError)):
        parse_document_bytes(b"%PDF-1.4 test", filename="a.pdf", engine="mineru")

