import inspect
import re
from typing import Any, Callable, Literal, Tuple, Type, TypeVar

from arclet.alconna import Args
from nepattern import (
    BasePattern,
    Empty,
    MatchMode,
    MatchFailed,
    all_patterns,
)
from nepattern.context import global_patterns
from tarina import lang
from .debug import analyse_args

TOrigin = TypeVar("TOrigin")


class ObjectPattern(BasePattern[TOrigin, Any, Literal[MatchMode.TYPE_CONVERT]]):
    def __init__(
        self,
        origin: Type[TOrigin],
        limit: Tuple[str, ...] = (),
        flag: Literal["urlget", "part", "json", "space"] = "part",
        **suppliers: Callable,
    ):
        self._args = Args()
        self._names = []
        pmap = all_patterns()
        for param in inspect.signature(origin.__init__).parameters.values():
            name = param.name
            anno = param.annotation
            default = param.default
            if name in ("self", "cls"):
                continue
            if limit and name not in limit:
                continue
            if param.kind in (
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            ):
                continue
            if anno is Empty:
                anno = pmap[str]
            elif inspect.isclass(anno) and issubclass(anno, str):
                anno = pmap[str]
            elif inspect.isclass(anno) and issubclass(anno, int):
                anno = pmap[int]
            if name in suppliers and inspect.isclass(anno):
                _s_sig = inspect.signature(suppliers[name])
                if len(_s_sig.parameters) == 1 or (
                    len(_s_sig.parameters) == 2 and inspect.ismethod(suppliers[name])
                ):
                    anno = BasePattern(
                        mode=MatchMode.TYPE_CONVERT,
                        origin=Any,  # type: ignore
                        converter=lambda _, x: suppliers[name](x),
                        alias=anno.__name__,
                    )
                elif len(_s_sig.parameters) == 0 or (
                    len(_s_sig.parameters) == 1 and inspect.ismethod(suppliers[name])
                ):
                    default = suppliers[name]()
                else:
                    raise TypeError(lang.require("tools", "pattern.supplier_params_error"))
            self._names.append(name)
            self._args.add(name, value=anno, default=default)
        self.flag = flag
        if flag == "part":
            self._re_pattern = re.compile(
                ";".join(f"(?P<{i}>.+?)" for i in self._names)
            )
        elif flag == "space":
            self._re_pattern = re.compile(
                "( )".join(f"(?P<{i}>.+?)" for i in self._names)
            )
        elif flag == "urlget":
            self._re_pattern = re.compile(
                "&".join(f"{i}=(?P<{i}>.+?)" for i in self._names)
            )
        elif flag == "json":
            self._re_pattern = re.compile(
                r"\{"
                + ",".join(f"\\'{i}\\':\\'(?P<{i}>.+?)\\'" for i in self._names)
                + "}"
            )
        else:
            raise TypeError(lang.require("tools", "pattern.flag_error").format(target=flag))
        super().__init__(
            mode=MatchMode.TYPE_CONVERT, origin=origin, alias=origin.__name__
        )
        global_patterns().set(self)

    def match(self, input_: Any) -> TOrigin:
        if isinstance(input_, self.origin):
            return input_  # type: ignore
        elif not isinstance(input_, str):
            raise MatchFailed(lang.require("nepattern", "type_error").format(target=input_.__class__))
        if not (mat := self._re_pattern.fullmatch(input_)):
            raise MatchFailed(lang.require("nepattern", "content_error").format(target=input_))
        if res := analyse_args(
            self._args, list(mat.groupdict().values()), raise_exception=False
        ):
            return self.origin(**res)
        else:
            raise MatchFailed(lang.require("nepattern", "content_error").format(target=input_))

    def __call__(self, *args, **kwargs):
        return self.origin(*args, **kwargs)

    def __eq__(self, other):
        return isinstance(other, ObjectPattern) and self.origin == other.origin
