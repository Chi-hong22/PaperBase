"""CSL JSON Schema 定义

基于 Citation Style Language (CSL) 标准
https://citeproc-js.readthedocs.io/
"""

from pydantic import BaseModel, Field


class CSLName(BaseModel):
    """CSL 名称格式"""
    family: str
    given: str | None = None

    model_config = {"extra": "allow"}


class CSLDate(BaseModel):
    """CSL 日期格式"""
    date_parts: list[list[int]] = Field(alias="date-parts")

    model_config = {"populate_by_name": True}


class CSLItem(BaseModel):
    """CSL Item 完整格式"""
    type: str  # article-journal, book, paper-conference, etc.
    id: str
    title: str
    author: list[CSLName]
    issued: CSLDate

    # Optional fields
    DOI: str | None = None
    container_title: str | None = Field(None, alias="container-title")
    volume: str | None = None
    issue: str | None = None
    page: str | None = None
    publisher: str | None = None
    ISSN: str | None = None
    URL: str | None = None
    abstract: str | None = None

    model_config = {
        "populate_by_name": True,
        "extra": "allow"
    }
