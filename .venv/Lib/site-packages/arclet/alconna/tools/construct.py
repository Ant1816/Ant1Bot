import asyncio
import inspect
import re
import sys
import typing
from contextlib import suppress
from dataclasses import dataclass, field, asdict
from functools import partial, wraps
from types import FunctionType, MethodType, ModuleType
from typing import (
    Any,
    Callable,
    Dict,
    Generic,
    List,
    Literal,
    Mapping,
    Optional,
    Type,
    TypeVar,
    Union,
    cast,
    TypedDict,
    overload
)

from arclet.alconna import Namespace
from arclet.alconna.args import ArgFlag, Args, Arg
from arclet.alconna.action import Action
from arclet.alconna.arparma import Arparma, ArparmaBehavior
from arclet.alconna.base import Option, Subcommand
from arclet.alconna.model import OptionResult
from arclet.alconna.core import Alconna
from arclet.alconna.exceptions import NullMessage
from arclet.alconna.manager import command_manager, ShortcutArgs
from arclet.alconna.typing import TDC, TAValue, KeyWordVar, MultiVar, CommandMeta, AllParam, ShortcutRegWrapper, StrMulti
from nepattern import ANY, all_patterns, type_parser, RawStr, TPattern
from tarina import split, split_once, init_spec, lang, Empty
from typing_extensions import get_origin, NotRequired, Self

T = TypeVar("T")
TCallable = TypeVar("TCallable", bound=Callable)

PARSER_TYPE = Callable[
    [Callable[..., T], Arparma, Dict[str, Any], asyncio.AbstractEventLoop],
    T,
]


def default_parser(
    func: Callable[..., T],
    result: Arparma,
    local_arg: Dict[str, Any],
    loop: asyncio.AbstractEventLoop,
) -> T:
    return result.call(func)


class Executor(Generic[T]):
    """
    以 click-like 方法创建的 Alconna 结构体, 可以被视为一类 CommanderHandler
    """

    command: Alconna
    parser_func: Callable[
        [Callable[..., T], Arparma, Dict[str, Any], asyncio.AbstractEventLoop],
        T,
    ]
    local_args: Dict[str, Any]
    exec_target: Callable[..., T]

    def __init__(self, command: Alconna, target: Callable):
        self.command = command
        self.exec_target = target
        self.parser_func = default_parser
        self.local_args = {}

    def set_local_args(self, local_args: Optional[Dict[str, Any]] = None):
        """
        设置本地参数

        Args:
            local_args (Optional[Dict[str, Any]]): 本地参数
        """
        self.local_args = local_args or {}

    def set_parser(self, parser_func: PARSER_TYPE):
        """
        设置解析器

        Args:
            parser_func (PARSER_TYPE): 解析器, 接受的参数必须为 (func, args, local_args, loop)
        """
        self.parser_func = parser_func
        return self

    def __call__(self, message: TDC) -> Arparma[TDC]:
        if not self.exec_target:
            raise RuntimeError(lang.require("tools", "construct.decorate_error"))
        result = self.command.parse(message)
        if result.matched:
            self.parser_func(
                self.exec_target,
                result,
                self.local_args,
                asyncio.get_event_loop(),
            )
        return result

    def from_commandline(self):
        """从命令行解析参数"""
        if not self.command:
            raise RuntimeError(lang.require("tools", "construct.decorate_error"))
        args = sys.argv[1:]
        args.insert(0, self.command.command)
        return self.__call__(" ".join(args))


# ----------------------------------------
# click-like
# ----------------------------------------


class AlconnaDecorate:
    """
    Alconna Click-like 构造方法的生成器

    Examples:
        >>> cli = AlconnaDecorate()
        >>> @cli.command()
        ... @cli.option("--name|-n", Args["name", str, "your name"])
        ... @cli.option("--age|-a", Args["age", int, "your age"])
        ... def hello(name: str, age: int):
        ...     print(f"Hello {name}, you are {age} years old.")
        ...
        >>> hello("hello --name Alice --age 18")

    Attributes:
        namespace (str): 命令的命名空间
    """

    namespace: str
    building: bool
    buffer: Dict[str, Any]
    default_parser: PARSER_TYPE

    def __init__(self, namespace: str = "Alconna"):
        """
        初始化构造器

        Args:
            namespace (str): 命令的命名空间
        """
        self.namespace = namespace
        self.building = False
        self.buffer = {}
        self.default_parser = default_parser

    def command(
        self,
        name: Optional[str] = None,
        headers: Optional[List[Any]] = None,
    ) -> Callable[[Callable[..., T]], Executor[T]]:
        """
        开始构建命令

        Args:
            name (Optional[str]): 命令名称
            headers (Optional[List[Any]]): 命令前缀
        """
        self.building = True

        def wrapper(func: Callable[..., T]) -> Executor[T]:
            alc = Alconna(
                name or func.__name__,
                headers or [],
                self.buffer.pop("args", Args()),
                *self.buffer.pop("options", []),
                meta=self.buffer.pop("meta", CommandMeta()),
                namespace=self.namespace,
            )
            if alc.meta.example and "$" in alc.meta.example:
                alc.meta.example = alc.meta.example.replace("$", str(alc.prefixes[0]) if alc.prefixes else "")
            self.building = False
            return Executor(alc, func).set_parser(self.default_parser)

        return wrapper

    @init_spec(Option, True)
    def option(self, opt: Option) -> Callable[[TCallable], TCallable]:
        """
        添加命令选项

        """
        if not self.building:
            raise RuntimeError(lang.require("tools", "construct.decorate_error"))

        def wrapper(func: TCallable) -> TCallable:
            self.buffer.setdefault("options", []).append(opt)
            return func

        return wrapper

    @init_spec(Subcommand, True)
    def subcommand(self, sub: Subcommand) -> Callable[[TCallable], TCallable]:
        """
        添加命令选项

        """
        if not self.building:
            raise RuntimeError(lang.require("tools", "construct.decorate_error"))

        def wrapper(func: TCallable) -> TCallable:
            self.buffer.setdefault("options", []).append(sub)
            return func

        return wrapper

    def main_args(self, args: Args) -> Callable[[TCallable], TCallable]:
        """
        添加命令参数

        Args:
            args (Args): 参数
        """
        if not self.building:
            raise RuntimeError(lang.require("tools", "construct.decorate_error"))

        def wrapper(func: TCallable) -> TCallable:
            self.buffer["args"] = args
            return func

        return wrapper

    @init_spec(Args, True)
    def argument(self, arg: Args) -> Callable[[TCallable], TCallable]:
        """
        添加命令参数
        """
        if not self.building:
            raise RuntimeError(lang.require("tools", "construct.decorate_error"))

        def wrapper(func: TCallable) -> TCallable:
            if args := self.buffer.get("args"):  # type: ignore
                args: Args
                args.__merge__(arg)
            else:
                self.buffer["args"] = Args().__merge__(arg)
            return func

        return wrapper

    def meta(self, content: CommandMeta) -> Callable[[TCallable], TCallable]:
        """
        添加命令元数据
        """
        if not self.building:
            raise RuntimeError(lang.require("tools", "construct.decorate_error"))

        def wrapper(func: TCallable) -> TCallable:
            self.buffer["meta"] = content
            return func

        return wrapper

    def help(
        self,
        description: str,
        usage: Optional[str] = None,
        example: Optional[str] = None,
    ) -> Callable[[TCallable], TCallable]:
        """
        添加命令元数据
        """
        if not self.building:
            raise RuntimeError(lang.require("tools", "construct.decorate_error"))

        def wrapper(func: TCallable) -> TCallable:
            self.buffer["meta"] = CommandMeta(description, usage, example)
            return func

        return wrapper

    def set_default_parser(self, parser_func: PARSER_TYPE):
        """
        设置默认的参数解析器

        Args:
            parser_func (PARSER_TYPE): 参数解析器, 接受的参数必须为 (func, args, local_args, loop)
        """
        self.default_parser = parser_func
        return self


def args_from_list(args: List[List[str]], custom_types: Dict[str, type]) -> Args:
    """
    从处理好的字符串列表中生成Args

    Examples:
        >>> args_from_list([["foo", "str"], ["bar", "digit", "123"]], {"digit":int})
        Args(foo: str, bar: int = 123)
        >>> args_from_list([["foo", "str+"]])
        Args(foo: (str+))
    """
    _args = Args()
    for arg in args:
        if (_le := len(arg)) == 0:
            raise NullMessage
        default = arg[2].strip(" ") if _le > 2 else Empty
        name = arg[0].strip(" ")
        value = (
            AllParam
            if name.startswith("...") else
            (arg[1].strip(" ") if _le > 1 else ANY)
        )
        name = name.replace("...", "")
        _multi, _kw, _slice = "", False, -1
        if isinstance(value, str):
            if mat := re.match(
                r"^(?P<name>.+?)(?P<multi>[+*]+)(\[)?(?P<slice>\d*)(])?$", value
            ):
                value = mat["name"]
                _multi = mat["multi"][0]
                _kw = len(mat["multi"]) > 1
                _slice = int(mat["slice"] or -1)
            elif value in ("+str", "mstr", "strm"):
                value = "StrMulti"
            with suppress(NameError, ValueError, TypeError):
                _types = custom_types.copy()
                _types.update(typing.__dict__)
                _types["StrMulti"] = StrMulti  # type: ignore
                value = all_patterns().get(value, None) or type_parser(eval(value, _types))  # type: ignore
                default = (
                    (get_origin(value.origin) or value.origin)(default)
                    if default is not Empty
                    else default
                )
            if _multi:
                value = MultiVar(
                    KeyWordVar(value) if _kw else value, _slice if _slice > 1 else _multi,  # type: ignore
                )
        _args.add(name, value=value, default=default)  # type: ignore
    return _args


def args_from_string(string: str, formats: Mapping[str, Union[TAValue, Args, Arg]], args: Args):
    if mat := re.match(r"^\{(?P<pattern>.+?)}$", string):
        pat = mat["pattern"]
        if pat in formats:
            value = formats[pat]
            if isinstance(value, (Args, Arg)):
                args.__merge__(value)
            else:
                args.__merge__([pat, value])
        else:
            part = re.split("[:=]", pat)
            if len(part) == 1:
                args.__merge__([part[0], ANY])
            else:
                args.__merge__(args_from_list([part], {}))
    else:
        args.__merge__([string, RawStr(string)])


def alconna_from_format(
    format_string: str,
    format_args: Optional[Mapping[str, Union[TAValue, Args, Arg]]] = None,
    meta: Optional[CommandMeta] = None,
    union: bool = True,
) -> "Alconna":
    """
    以格式化字符串的方式构造 Alconna

    该方法建议使用多个重名的命令时使用

    Examples:

        >>> alc1 = AlconnaFormat(
        ...     "lp user {target:str} perm set {perm:str} {default}",
        ...     {"default": Args["val", bool, True]},
        ... )
        >>> alc2 = AlconnaFormat(
        ...     "lp user {target:str} perm del {perm:str}",
        ... )
        >>> alc3 = AlconnaFormat(
        ...     "lp user {target:str} perm info {perm:str}"
        ... )
        >>> alc1.parse("lp user AAA perm set admin.all False")
        >>> alc1.parse("lp user AAA perm info admin.all")
    """
    formats = format_args or {}
    _key_ref = 0
    strings = split(format_string.replace("{", "\"{").replace("}", "}\""), " ")
    command = strings.pop(0)
    data = []
    if mat := re.match(r"^\[(.+?)]$", command):
        data.append([i.strip() for i in mat["data"].split("|")])
    else:
        data.append(command)
    main_args = Args()
    _finish_arg = False
    _stack = []
    for string in strings:
        if string.startswith("-"):
            _finish_arg = True
            _stack.append(string)
            continue
        if not _finish_arg:
            args_from_string(string, formats, main_args)
        elif not _stack:
            raise ValueError(lang.require("tools", "construct.format_error".format(target=string)))
        else:
            singles = _stack[:-1]
            name = _stack[-1]
            _opt_args = Args()
            args_from_string(string, formats, _opt_args)
            data.extend(Option(single) for single in singles)
            data.append(Option(name, _opt_args))
    alc = Alconna(main_args, *data, meta=meta)
    if union:
        with suppress(ValueError):
            cmd = command_manager.get_command(alc.path)
            cmd = cmd | alc
            return cmd
    return alc


class AlconnaString:
    """以纯字符串的形式构造Alconna的简易方式, 或者说是koishi-like的方式

    Examples:

        >>> alc = (
        ...     AlconnaString("test <message:str:hello> #HELP_STRING")
        ...     .option("foo", "-f <val:bool>")
        ...     .option("bar", "-bar <bar:str> [baz:int]")
        ...     .option("qux", default=123)
        ...     .build()
        ... )
        >>> alc.parse("test abcd --foo True")
    """
    @staticmethod
    def args_gen(pattern: str, types: dict):
        args = Args()
        temp = []
        quote = False
        for char in pattern:
            if char == " " and not quote:
                if temp:
                    args.__merge__([temp[0], RawStr(temp[0])])
                    temp.clear()
                continue
            if char in {"<", "["}:  # start
                quote = True
                temp.append("")
            elif char == ">":
                args.__merge__(args_from_list([temp], types.copy()))
                temp.clear()
                quote = False
            elif char == "]":
                temp[0] = f"{temp[0]};?"
                args.__merge__(args_from_list([temp], types.copy()))
                temp.clear()
                quote = False
            elif char in {":", "="}:
                temp.append("")
            elif not temp:
                temp.append(char)
            else:
                temp[-1] += char
        return args

    def __init__(self, command: str, help_text: Optional[str] = None, meta: Optional[CommandMeta] = None):
        """创建 AlconnaString

        Args:
            command (str): 命令字符串, 例如 `test <message:str:hello> #HELP_STRING`
            help_text (Optional[str], optional): 选填的命令的帮助文本.
            meta (Optional[CommandMeta], optional): 选填的命令元数据.
        """
        self.buffer = {}
        self.options = []
        self.shortcuts = []
        self.actions = []
        head, others = split_once(command, " ")
        self.meta = CommandMeta(fuzzy_match=True) if meta is None else CommandMeta(**asdict(meta))
        if help_text:
            self.meta.description = help_text
        elif self.meta.description == "Unknown":
            self.meta.description = head
        if mat := re.match(r"^\[(.+?)]", head):
            self.buffer["prefixes"] = mat[1].split("|")
            head = head[mat.end():]
        self.buffer["command"] = head.lstrip()
        if help_string := re.findall(r"(?: )#(.+)$", others):  # noqa
            self.meta.description = help_string[0]
            others = others[: -len(help_string[0]) - 1].rstrip()
        custom_types = getattr(inspect.getmodule(inspect.stack()[1][0]), "__dict__", {})
        self.buffer["main_args"] = self.args_gen(others, custom_types.copy())

    def alias(self, *alias: str) -> Self:
        for al in alias:
            self.shortcut(al, {"prefix": True})
        return self

    def config(
        self,
        fuzzy_match: bool = False,
        fuzzy_threshold: float = 0.6,
        raise_exception: bool = False,
        hide: bool = False,
        hide_shortcut: bool = False,
        keep_crlf: bool = False,
        compact: bool = False,
        strict: bool = True,
        context_style: Optional[Literal["bracket", "parentheses"]] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Self:
        """设置命令的元数据

        Args:
            fuzzy_match (bool, optional): 是否开启模糊匹配. Defaults to False.
            fuzzy_threshold (float, optional): 模糊匹配阈值. Defaults to 0.6.
            raise_exception (bool, optional): 是否抛出异常. Defaults to False.
            hide (bool, optional): 是否对manager隐藏. Defaults to False.
            hide_shortcut (bool, optional): 快捷指令是否在help信息中隐藏. Defaults to False.
            keep_crlf (bool, optional): 是否保留换行字符. Defaults to False.
            compact (bool, optional): 是否允许第一个参数紧随头部. Defaults to False.
            strict (bool, optional): 是否严格匹配，若为 False 则未知参数将作为名为 $extra 的参数. Defaults to True.
            context_style (Optional[Literal["bracket", "parentheses"]], optional): 上下文插值的风格. Defaults to None.
            extra (Optional[Dict[str, Any]], optional): 额外的元数据. Defaults to None.
        """
        self.meta.fuzzy_match = fuzzy_match
        self.meta.fuzzy_threshold = fuzzy_threshold
        self.meta.raise_exception = raise_exception
        self.meta.hide = hide
        self.meta.hide_shortcut = hide_shortcut
        self.meta.keep_crlf = keep_crlf
        self.meta.compact = compact
        self.meta.strict = strict
        self.meta.context_style = context_style
        if extra:
            self.meta.extra.update(extra)
        return self

    def namespace(self, ns: Union[str, Namespace]):
        self.buffer["namespace"] = ns
        return self

    def option(self, name: str, opt: Optional[str] = None, default: Any = Empty, action: Optional[Action] = None) -> Self:
        """添加一个选项

        Args:
            name (str): 选项的实际名称
            opt (Optional[str], optional): 选项的字符串, 例如 `--foo -f <val:bool>`.
            default (Any, optional): 选项的默认值.
            action (Optional[Action], optional): 选项的动作.
        """
        _default = default
        if isinstance(default, dict):
            _default = OptionResult(args=default)
        if opt is None:
            self.options.append(
                Option(name, default=_default, action=action)
            )
            return self
        help_text = None
        if help_string := re.findall(r"(?: )?#(.+)$", opt):  # noqa
            help_text = help_string[0]
            opt = opt[: -len(help_string[0]) - 1].rstrip()
        parts = split(opt, " ")
        aliases = [f"--{name}"]
        index = 0
        for part in parts:
            if part.startswith("<") or part.startswith("[") or part.startswith("#"):
                break
            aliases.append(part)
            index += 1
        _args = Args()
        if parts[index:]:
            custom_types = getattr(inspect.getmodule(inspect.stack()[1][0]), "__dict__", {})
            _args = self.args_gen(" ".join(parts[index:]), custom_types.copy())
        _opt = Option("|".join(aliases), _args, dest=name, default=_default, action=action, help_text=help_text)
        self.options.append(_opt)
        return self

    def subcommand(self, name: str, default: Any = Empty) -> Self:
        """添加一个子命令

        Args:
            name (str): 子命令的名称
            default (Any, optional): 子命令的默认值.
        """
        _default = default
        if isinstance(default, dict):
            _default = OptionResult(args=default)
        help_text = None
        if help_string := re.findall(r"(?: )#(.+)$", name):  # noqa
            help_text = help_string[0]
            name = name[: -len(help_string[0]) - 1].rstrip()
        parts = split(name, " ")
        aliases = []
        index = 0
        for part in parts:
            if part.startswith("<") or part.startswith("["):
                break
            aliases.append(part)
            index += 1
        _args = Args()
        if parts[index:]:
            custom_types = getattr(inspect.getmodule(inspect.stack()[1][0]), "__dict__", {})
            _args = self.args_gen(" ".join(parts[index:]), custom_types.copy())
        _opt = Subcommand("|".join(aliases), _args, dest=name, default=_default, help_text=help_text)
        return self

    def usage(self, content: str) -> Self:
        """设置命令的使用方法"""
        self.meta.usage = content
        return self

    def example(self, content: str) -> Self:
        """设置命令的使用示例"""
        if not self.meta.example:
            self.meta.example = content
        else:
            self.meta.example += f"\n{content}"
        return self

    @overload
    def shortcut(self, key: Union[str, TPattern], args: Optional[ShortcutArgs] = None) -> Self:
        """设置命令的快捷方式

        Args:
            key (str | re.Pattern[str]): 快捷命令名, 可传入正则表达式
            args (ShortcutArgs): 快捷命令参数, 不传入时则尝试使用最近一次使用的命令
        """
        ...

    @overload
    def shortcut(
        self,
        key: Union[str, TPattern],
        *,
        command: Optional[str] = None,
        arguments: Optional[list] = None,
        fuzzy: bool = True,
        prefix: bool = False,
        wrapper: Optional[ShortcutRegWrapper] = None,
        humanized: Optional[str] = None,
    ) -> Self:
        """设置命令的快捷方式

        Args:
            key (str | re.Pattern[str]): 快捷命令名, 可传入正则表达式
            command (str): 快捷命令指向的命令
            arguments (list[Any] | None, optional): 快捷命令参数, 默认为 `None`
            fuzzy (bool, optional): 是否允许命令后随参数, 默认为 `True`
            prefix (bool, optional): 是否调用时保留指令前缀, 默认为 `False`
            wrapper (ShortcutRegWrapper, optional): 快捷指令的正则匹配结果的额外处理函数, 默认为 `None`
            humanized (str, optional): 快捷指令的人类可读描述, 默认为 `None`
        """
        ...

    def shortcut(self, key: Union[str, TPattern], args: Optional[ShortcutArgs] = None, **kwargs) -> Self:
        """设置命令的快捷方式"""
        self.shortcuts.append((key, args, kwargs))
        return self

    def action(self, func: Callable) -> Self:
        """设置命令的动作"""
        self.actions.append(func)
        return self

    def build(self):
        """构造为 Alconna 对象"""
        ns = self.buffer.pop("namespace", None)
        alc = Alconna(*self.buffer.values(), *self.options, namespace=ns, meta=self.meta)
        for key, args, kwargs in self.shortcuts:
            alc.shortcut(key, args, **kwargs)  # type: ignore
        for action in self.actions:
            alc.bind()(action)
        return alc


class MountConfig(TypedDict):
    prefixes: NotRequired[List[str]]
    raise_exception: NotRequired[bool]
    description: NotRequired[str]
    namespace: NotRequired[str]
    command: NotRequired[str]


config_keys = ("prefixes", "raise_exception", "description", "namespace", "command")


def visit_config(obj: Any, base: Optional[MountConfig] = None) -> MountConfig:
    result: MountConfig = base or {}
    if isinstance(obj, (FunctionType, MethodType)):
        codes, _ = inspect.getsourcelines(obj)
        _get_config = False
        _start_indent = 0
        for line in codes:
            indent = len(line) - len(line.lstrip())
            if line.lstrip().startswith("class") and line.lstrip().rstrip(
                "\n"
            ).endswith("Config:"):
                _get_config = True
                _start_indent = indent
                continue
            if _get_config:
                if indent == _start_indent:
                    break
                if line.lstrip().startswith("def"):
                    continue
                _contents = re.split(r"\s*=\s*", line.strip())
                if len(_contents) == 2 and _contents[0] in config_keys:
                    result[_contents[0]] = eval(_contents[1])  # type: ignore
    elif kss := inspect.getmembers(
        obj, lambda x: inspect.isclass(x) and x.__name__.endswith("Config")
    ):
        ks = kss[0][1]
        result.update({k: getattr(ks, k) for k in config_keys if k in dir(ks)})  # type: ignore
    return result


@dataclass(unsafe_hash=True)
class CallbackHandler(ArparmaBehavior):
    main_call: Optional[Callable] = field(default=None)
    options: Dict[str, Callable] = field(default_factory=dict, hash=False)
    results: Dict[str, Any] = field(default_factory=dict, hash=False)

    def before_operate(self, interface: Arparma):
        super().before_operate(interface)
        self.results.clear()

    def operate(self, interface: Arparma):
        if call := self.main_call:
            call(**interface.main_args)
        for path, action in self.options.items():
            if (d := interface.query(path, None)) is not None:
                self.results[action.__qualname__] = action(**d)


class SubClassMounter(Subcommand):
    instance: Any

    def _get_instance(self):
        return self.instance

    def _inject_instance(self, target: Callable):
        @wraps(target)
        def wrapper(*args, **kwargs):
            return target(self._get_instance(), *args, **kwargs)

        return wrapper

    def __init__(self, mount_cls: Type, upper_handler: CallbackHandler, upper_path: str):
        self.mount_cls = mount_cls
        config = visit_config(mount_cls)
        members = inspect.getmembers(
            mount_cls, lambda x: inspect.isfunction(x) or inspect.ismethod(x)
        )

        _options = []
        main_help_text = (
            mount_cls.__doc__ or mount_cls.__init__.__doc__ or mount_cls.__name__
        )

        main_args = Args.from_callable(mount_cls.__init__)[0]

        def _main_func(**kwargs):
            if hasattr(self, "instance"):
                for k, v in kwargs.items():
                    setattr(self.instance, k, v)
            else:
                self.instance = mount_cls(**kwargs)
                for key, value in kwargs.items():
                    self.args[key].field.default = value  # type: ignore

        path = f"subcommands.{upper_path}.{mount_cls.__name__}" if upper_path else f"subcommands.{mount_cls.__name__}"
        upper_handler.options[f"{path}.args"] = _main_func
        for name, func in filter(lambda x: not x[0].startswith("_"), members):
            help_text = func.__doc__ or name
            _opt_args, method = Args.from_callable(func)
            if method:
                func = self._inject_instance(func)
            _options.append(
                Option(name, _opt_args, help_text=help_text)
            )
            upper_handler.options[f"{path}.options.{name}.args"] = func

        _options.extend(
            SubClassMounter(cls, upper_handler, path)
            for name, cls in inspect.getmembers(mount_cls, inspect.isclass)
            if not name.startswith("_") and not name.endswith("Config")
        )

        super().__init__(
            config.get("command", mount_cls.__name__),
            main_args,
            *_options,
            help_text=config.get("description", main_help_text),
        )


class FuncMounter(Alconna[TDC], Generic[T, TDC]):
    def __init__(
        self, func: Callable[..., T], config: Optional[MountConfig] = None
    ):
        config = visit_config(func, config)
        func_name = func.__name__
        if func_name.startswith("_"):
            raise ValueError(lang.require("tools", "construct.func_name_error"))
        _args, method = Args.from_callable(func)
        if method and isinstance(func, MethodType):
            self.instance = func.__self__
            func = cast(FunctionType, partial(func, self.instance))
        super(FuncMounter, self).__init__(
            config.get("prefixes", []),
            config.get("command", func_name),
            _args,
            meta=CommandMeta(
                description=config.get("description", func.__doc__ or func_name),
                raise_exception=config.get("raise_exception", True),
            ),
            namespace=config.get("namespace", None),
        )
        self.bind()(func)

    @property
    def exec_result(self) -> Dict[str, T]:
        return {ext.target.__name__: res for ext, res in self._executors.items() if res is not None}


class ModuleMounter(Alconna):
    def __init__(self, module: ModuleType, config: Optional[MountConfig] = None):
        self.mount_cls = module.__class__
        self.instance = module
        config = config or visit_config(module, config)
        _options = []
        members = inspect.getmembers(
            module, lambda x: inspect.isfunction(x) or inspect.ismethod(x)
        )
        self.cb_behavior = CallbackHandler()
        for name, func in members:
            if name.startswith("_") or func.__name__.startswith("_"):
                continue
            help_text = func.__doc__ or name
            _opt_args, method = Args.from_callable(func)
            if method:
                func = partial(func, func.__self__)
            _options.append(
                Option(
                    name, args=_opt_args, help_text=help_text
                )
            )
            self.cb_behavior.options[f"options.{name}.args"] = func
        _options.extend(
            SubClassMounter(cls, self.cb_behavior, "")
            for name, cls in inspect.getmembers(module, inspect.isclass)
            if not name.startswith("_") and not name.endswith("Config")
        )
        super().__init__(
            config.get("command", module.__name__),
            config.get("prefixes", []),
            *_options,
            namespace=config.get("namespace", None),
            meta=CommandMeta(
                description=config.get(
                    "description", module.__doc__ or module.__name__
                ),
                raise_exception=config.get("raise_exception", True),
            ),
            behaviors=[self.cb_behavior],
        )

    def get_result(self, func: Callable):
        return self.cb_behavior.results.get(func.__qualname__)


class ClassMounter(Alconna[TDC], Generic[T, TDC]):
    mount_cls: Type[T]
    instance: T

    def _get_instance(self) -> T:
        return self.instance

    def _inject_instance(self, target: Callable):
        @wraps(target)
        def wrapper(*args, **kwargs):
            return target(self._get_instance(), *args, **kwargs)

        return wrapper

    def __init__(self, mount_cls: Type[T], config: Optional[MountConfig] = None):
        self.mount_cls = mount_cls
        config = config or visit_config(mount_cls, config)
        members = inspect.getmembers(
            mount_cls, lambda x: inspect.isfunction(x) or inspect.ismethod(x)
        )

        _options = []
        main_help_text = (
            mount_cls.__doc__ or mount_cls.__init__.__doc__ or mount_cls.__name__
        )

        main_args = Args.from_callable(mount_cls.__init__)[0]

        def _main_func(**kwargs):
            if hasattr(self, "instance"):
                for k, v in kwargs.items():
                    setattr(self.instance, k, v)
            else:
                self.instance = mount_cls(**kwargs)
                for key, value in kwargs.items():
                    self.args[key].field.default = value  # type: ignore

        self.cb_behavior = CallbackHandler(main_call=_main_func)
        for name, func in filter(lambda x: not x[0].startswith("_"), members):
            help_text = func.__doc__ or name
            _opt_args, method = Args.from_callable(func)
            if method:
                func = self._inject_instance(func)
            _options.append(
                Option(name, _opt_args, help_text=help_text)
            )
            self.cb_behavior.options[f"options.{name}.args"] = func

        _options.extend(
            SubClassMounter(cls, self.cb_behavior, "")
            for name, cls in inspect.getmembers(mount_cls, inspect.isclass)
            if not name.startswith("_") and not name.endswith("Config")
        )
        super().__init__(
            config.get("command", mount_cls.__name__),
            main_args,
            config.get("prefixes", []),
            *_options,
            namespace=config.get("namespace", None),
            meta=CommandMeta(
                description=config.get("description", main_help_text),
                raise_exception=config.get("raise_exception", True),
            ),
            behaviors=[self.cb_behavior],
        )

    def get_result(self, func: Callable):
        return self.cb_behavior.results.get(func.__qualname__)


class ObjectMounter(Alconna[TDC], Generic[T, TDC]):
    mount_cls: Type[T]
    instance: T

    def __init__(self, obj: T, config: Optional[MountConfig] = None):
        self.mount_cls = type(obj)
        self.instance = obj
        config = config or visit_config(obj)
        obj_name = obj.__class__.__name__
        members = inspect.getmembers(
            obj, lambda x: inspect.isfunction(x) or inspect.ismethod(x)
        )
        _options = []
        main_help_text = obj.__doc__ or obj.__init__.__doc__ or obj_name

        def _main_func(**kwargs):
            for k, v in kwargs.items():
                setattr(self.instance, k, v)

        self.cb_behavior = CallbackHandler(main_call=_main_func)

        for name, func in filter(lambda x: not x[0].startswith("_"), members):
            help_text = func.__doc__ or name
            _opt_args, _ = Args.from_callable(func)
            _options.append(
                Option(
                    name, args=_opt_args, help_text=help_text
                )
            )
            self.cb_behavior.options[f"options.{name}.args"] = func

        _options.extend(
            SubClassMounter(cls, self.cb_behavior, "")
            for name, cls in inspect.getmembers(obj, inspect.isclass)
            if not name.startswith("_") and not name.endswith("Config")
        )
        main_args = Args.from_callable(obj.__init__)[0]
        for arg in main_args.argument:
            if hasattr(self.instance, arg.name):
                arg.field.default = getattr(self.instance, arg.name)

        super().__init__(
            config.get("command", obj_name),
            main_args,
            config.get("prefixes", []),
            *_options,
            meta=CommandMeta(
                description=config.get("description", main_help_text),
                raise_exception=config.get("raise_exception", True),
            ),
            behaviors=[self.cb_behavior],
            namespace=config.get("namespace", None),
        )

    def get_result(self, func: Callable):
        return self.cb_behavior.results.get(func.__qualname__)


@overload
def alconna_from_object(  # type: ignore
    target: ModuleType, command: Optional[TDC] = None, config: Optional[MountConfig] = None,
) -> ModuleMounter:
    ...


@overload
def alconna_from_object(  # type: ignore
    target: Type[T], command: Optional[TDC] = None, config: Optional[MountConfig] = None,
) -> ClassMounter[T, TDC]:
    ...


@overload
def alconna_from_object(
    target: Union[Callable[..., T], FunctionType], command: Optional[TDC] = None, config: Optional[MountConfig] = None,
) -> FuncMounter[T, TDC]:
    ...


@overload
def alconna_from_object(
    target: T, command: Optional[TDC] = None, config: Optional[MountConfig] = None,
) -> ObjectMounter[T, TDC]:
    ...


def alconna_from_object(  # type: ignore
    target: Optional[Union[Type[T], T, Callable[..., T], ModuleType]] = None,
    command: Optional[TDC] = None,
    config: Optional[MountConfig] = None,
) -> Union[
    ModuleMounter,
    ClassMounter[T, TDC],
    FuncMounter[T, TDC],
    ObjectMounter[T, TDC],
]:
    """
    通过解析传入的对象，生成 Alconna 实例的方法, 或者说是Fire-like的方式

    Examples:

        >>> def test_func(a, b, c):
        ...     print(a, b, c)
        ...
        >>> alc = AlconnaFire(test_func)
        >>> alc.parse("test_func 1 2 3")
    """
    if inspect.isfunction(target) or inspect.ismethod(target):
        r = FuncMounter(target, config)
    elif inspect.isclass(target):
        r = ClassMounter(target, config)
    elif inspect.ismodule(target):
        r = ModuleMounter(target, config)
    elif target:
        r = ObjectMounter(target, config)
    else:
        r = ModuleMounter(
            inspect.getmodule(inspect.stack()[1][0]) or sys.modules["__main__"], config
        )
    command = command or (" ".join(sys.argv[1:]) if len(sys.argv) > 1 else None)  # type: ignore
    if command:
        with suppress(Exception):
            r.parse(command)
        command_manager.require(r).reset()
    return r  # type: ignore


def delegate(cls: Type) -> Alconna:
    attrs = inspect.getmembers(cls, predicate=lambda x: not inspect.isroutine(x))
    _help = cls.__doc__ or cls.__name__
    _main_args = None
    _options = []
    _headers = []
    for name, attr in filter(lambda x: not x[0].startswith("_"), attrs):
        if isinstance(attr, Args):
            _main_args = attr
        elif isinstance(attr, (Option, Subcommand)):
            _options.append(attr)
        elif name.startswith("prefix"):
            _headers.extend(attr if isinstance(attr, (list, tuple)) else [attr])
    return Alconna(
        cls.__name__,
        _main_args,
        _headers,
        *_options,
        meta=CommandMeta(description=_help),
    )


def _argument(
    name: str,
    *alias: str,
    dest: Optional[str] = None,
    value: Optional[Any] = str,
    default: Optional[Any] = None,
    description: Optional[str] = None,
    required: bool = True,
    action: Optional[Action] = None,
):
    """类似于 argparse.ArgumentParser.add_argument() 的方法"""
    opt = Option(
        name, alias=list(alias), dest=dest, help_text=description, action=action
    )
    opt.args.add(
        name.strip("-"),
        value=value,  # type: ignore
        default=default,
        flags=[] if required else [ArgFlag.OPTIONAL],
    )
    opt.nargs += 1
    return opt


AlconnaFormat = alconna_from_format
AlconnaFire = alconna_from_object
Argument = _argument
