from pathlib import Path
from typing import Any

from tarina import Empty as Empty  # noqa

from .base import ANY as ANY
from .base import AntiPattern as AntiPattern
from .base import AnyString as AnyString
from .base import BOOLEAN as BOOLEAN
from .base import BYTES as BYTES
from .base import DATETIME as DATETIME
from .base import DICT as DICT
from .base import DelimiterInt as DelimiterInt
from .base import DirectPattern as DirectPattern
from .base import DirectTypePattern as DirectTypePattern
from .base import EMAIL as EMAIL
from .base import FLOAT as FLOAT
from .base import HEX as HEX
from .base import HEX_COLOR as HEX_COLOR
from .base import INTEGER as INTEGER
from .base import IP as IP
from .base import IterMode as IterMode
from .base import LIST as LIST
from .base import MappingPattern as MappingPattern
from .base import NONE as NONE
from .base import NUMBER as NUMBER
from .base import PATH as PATH
from .base import PathFile as PathFile
from .base import RegexPattern as RegexPattern
from .base import SET as SET
from .base import STRING as STRING
from .base import SequencePattern as SequencePattern
from .base import SwitchPattern as SwitchPattern
from .base import TUPLE as TUPLE
from .base import URL as URL
from .base import UnionPattern as UnionPattern
from .base import WIDE_BOOLEAN as WIDE_BOOLEAN
from .base import combine as combine
from .context import Patterns as Patterns
from .context import all_patterns as all_patterns
from .context import create_local_patterns as create_local_patterns
from .context import global_patterns
from .context import local_patterns as local_patterns
from .context import reset_local_patterns as reset_local_patterns
from .context import switch_local_patterns as switch_local_patterns
from .core import BasePattern as BasePattern
from .core import MatchMode as MatchMode
from .core import ValidateResult as ValidateResult
from .exception import MatchFailed as MatchFailed
from .func import Dot as Dot
from .func import Filter as Filter
from .func import GetItem as GetItem
from .func import Index as Index
from .func import Join as Join
from .func import Lower as Lower
from .func import Map as Map
from .func import Reduce as Reduce
from .func import Slice as Slice
from .func import Step as Step
from .func import Sum as Sum
from .func import Upper as Upper
from .main import parser as parser
from .util import RawStr as RawStr
from .util import TPattern as TPattern

type_parser = parser

global_patterns().update(
    {
        Any: ANY,
        Ellipsis: ANY,
        object: ANY,
        "any": ANY,
        "any_str": AnyString,
        "email": EMAIL,
        "color": HEX_COLOR,
        "hex": HEX,
        "ip": IP,
        "url": URL,
        "...": ANY,
        "number": NUMBER,
        list: LIST,
        tuple: TUPLE,
        set: SET,
        dict: DICT,
        Path: PATH,
        "file": PathFile,
    }
)


global_patterns().sets([BYTES, STRING, INTEGER, FLOAT, BOOLEAN, DATETIME])
