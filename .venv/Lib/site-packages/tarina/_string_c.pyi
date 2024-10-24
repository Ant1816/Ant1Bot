CRLF: str
QUOTATION: dict[str, str]

def split(text: str, separator: str, crlf: bool = True) -> list[str]:
    """尊重引号与转义的字符串切分

    Args:
        text (str): 要切割的字符串
        separator (str): 切割符.
        crlf (bool): 是否去除 \n 与 \r，默认为 True

    Returns:
        List[str]: 切割后的字符串, 可能含有空格
    """
    ...

def split_once(text: str, separator: str, crlf: bool = True) -> tuple[str, str]:
    """尊重引号与转义的字符串切分, 只切割一次

    Args:
        text (str): 要切割的字符串
        separator (str): 切割符.
        crlf (bool): 是否去除 \n 与 \r，默认为 True
    Returns:
        Tuple[str, str]: 切割后的字符串, 可能含有空格
    """
    ...
