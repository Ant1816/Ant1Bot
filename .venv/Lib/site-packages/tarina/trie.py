"""
Trie data structure implementation, modified from github.com/google/tarina.trie
"""

from __future__ import annotations

__author__ = "Michal Nazarewicz <mina86@mina86.com>"
__copyright__ = "Copyright 2014 Google Inc."


import copy as _copy
import enum
from collections.abc import Generator, Iterable, Iterator, MutableMapping
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Final,
    Generic,
    Literal,
    Optional,
    Protocol,
    TypeVar,
    overload,
)

from typing_extensions import Self


class ShortKeyError(KeyError):
    """Raised when given key is a prefix of an existing longer key
    but does not have a value associated with itself."""


T = TypeVar("T")
_VT = TypeVar("_VT")
T_Copy = Callable[[T], T]


class Children(Protocol[_VT]):

    def __bool__(self) -> bool: ...
    def __len__(self) -> int: ...

    def items(self) -> Iterable[tuple[str, _Node[_VT]]]: ...

    def sorted_items(self) -> Iterable[tuple[str, _Node[_VT]]]: ...

    def pick(self) -> tuple[str, _Node[_VT]]: ...

    def get(self, step: str) -> _Node[_VT] | None: ...

    def add(self, parent: _Node[_VT], step: str) -> _Node[_VT]: ...

    def require(self, parent: _Node[_VT], step: str) -> _Node[_VT]: ...

    def merge(self, other: Children[_VT], queue: list[tuple[_Node[_VT], ...]]) -> Children[_VT]: ...

    def delete(self, parent: _Node[_VT], step: str) -> None: ...

    def copy(self: Self, make_copy: T_Copy, queue: list[tuple[_Node[_VT], ...]]) -> Self: ...


class _NoChildren(Children[_VT]):
    """Collection representing lack of any children.

    Also acts as an empty iterable and an empty iterator.  This isn’t the
    cleanest designs but it makes various things more concise and avoids object
    allocations in a few places.

    Don’t create objects of this type directly; instead use _EMPTY singleton.
    """

    __slots__ = ()

    def __bool__(self) -> Literal[False]:
        return False

    def __len__(self) -> Literal[0]:
        return 0

    def __iter__(self):
        return self

    def __next__(self):
        raise StopIteration()

    items = sorted_items = __iter__

    def pick(self) -> tuple[str, _Node[_VT]]:
        raise NotImplementedError()

    def get(self, step: str):
        return None

    def add(self, parent: _Node[_VT], step: str):
        node: _Node[_VT] = _Node()
        parent.children = _OneChild(step, node)
        return node

    require = add

    def merge(self, other: Children[_VT], queue: list[tuple[_Node[_VT], ...]]) -> Children[_VT]:
        return other

    def delete(self, parent: _Node[_VT], step: str) -> None:
        return

    def copy(self, make_copy, queue):
        return self

    def __deepcopy__(self, memo):
        return self

    # pick and delete aren’t implemented on purpose since it should never be
    # called on a node with no children.


_EMPTY: Final[_NoChildren] = _NoChildren()


class _OneChild(Children[_VT]):
    """Children collection representing a single child."""

    __slots__ = ("step", "node")

    def __init__(self, step: str, node: _Node[_VT]):
        self.step = step
        self.node = node

    def __bool__(self) -> Literal[True]:
        return True

    def __len__(self) -> Literal[1]:
        return 1

    def items(self):
        return ((self.step, self.node),)

    sorted_items = items

    def pick(self):
        return self.step, self.node

    def get(self, step):
        return self.node if step == self.step else None

    def add(self, parent: _Node[_VT], step: str):
        node: _Node[_VT] = _Node()
        parent.children = _Children((self.step, self.node), (step, node))
        return node

    def require(self, parent: _Node[_VT], step: str):
        return self.node if self.step == step else self.add(parent, step)

    def merge(self, other, queue):
        """Moves children from other into this object."""
        if isinstance(other, _OneChild) and other.step == self.step:
            queue.append((self.node, other.node))
            return self
        else:
            children = _Children((self.step, self.node))
            children.merge(other, queue)
            return children

    def delete(self, parent, step):
        parent.children = _EMPTY

    def copy(self, make_copy, queue):
        cpy = _OneChild(make_copy(self.step), self.node.shallow_copy(make_copy))
        queue.append((cpy.node,))
        return cpy


class _Children(Children[_VT]):
    """Children collection representing more than one child."""

    __slots__ = ("data",)

    def __init__(self, *items: tuple[str, _Node[_VT]]):
        self.data = dict(items)

    def __bool__(self) -> bool:
        return bool(self.data)

    def __len__(self) -> int:
        return len(self.data)

    def items(self):
        return self.data.items()

    def sorted_items(self):
        return sorted(self.items())

    def pick(self):
        return next(iter(self.items()))

    def get(self, step: str) -> _Node[_VT] | None:
        return self.data.get(step)

    def add(self, parent: _Node[_VT], step: str):
        self.data[step] = node = _Node()
        return node

    def require(self, parent: _Node[_VT], step: str):
        return self.data.setdefault(step, _Node())

    def merge(self, other, queue):
        """Moves children from other into this object."""
        for step, other_node in other.items():
            node = self.data.setdefault(step, other_node)
            if node is not other_node:
                queue.append((node, other_node))
        return self

    def delete(self, parent, step):
        del self.data[step]
        if len(self) == 1:
            parent.children = _OneChild(*self.data.popitem())

    def copy(self, make_copy, queue):
        cpy = _Children()
        cpy.data.update((make_copy(step), node.shallow_copy(make_copy)) for step, node in self.items())
        nodes = list(cpy.data.values())
        queue.append(tuple(nodes))
        return cpy


V = TypeVar("V")
V1 = TypeVar("V1")


class _SentinelClass(enum.Enum):
    _Sentinel = object()


T_Iteritems = Callable[[Children[T]], Iterable[tuple[str, "_Node[T]"]]]

PathConv = Callable[[tuple[str, ...]], str]
NodeFactory = Callable[
    [
        Callable[[tuple[str, ...]], str],
        tuple[str, ...],
        Generator["_Node[T]", None, None],
        Optional[T],
    ],
    "_Node[T]",
]


class _Node(Generic[V]):
    """A single node of a trie.

    Stores value associated with the node and dictionary of children.
    """

    __slots__ = ("children", "value")

    def __init__(self):
        self.children: Children[V] = _EMPTY
        self.value: V | Literal[_SentinelClass._Sentinel] = _SentinelClass._Sentinel

    def merge(self, other: _Node[V], overwrite: bool):
        """Move children from other node into this one.

        Args:
            other: Other node to move children and value from.
            overwrite: Whether to overwrite existing node values.
        """
        queue = [(self, other)]
        while queue:
            lhs, rhs = queue.pop()
            if lhs.value is _SentinelClass._Sentinel or (overwrite and rhs.value is not _SentinelClass._Sentinel):
                lhs.value = rhs.value
            if lhs.children is _EMPTY:
                lhs.children = rhs.children
            elif rhs.children is not _EMPTY:
                lhs.children = lhs.children.merge(rhs.children, queue)
            rhs.children = _EMPTY

    def iterate(
        self, path: list[str], shallow: bool, items: T_Iteritems[V]
    ) -> Generator[tuple[list[str], V], Any, None]:
        """Yields all the nodes with values associated to them in the trie.

        Args:
            path: Path leading to this node.  Used to construct the key when
                returning value of this node and as a prefix for children.
            shallow: Perform a shallow traversal, i.e. do not yield nodes if
                their prefix has been yielded.
            items: A callable which takes ``node.children`` as a sole argument
                and returns an iterable of children as ``(step, node)`` pairs.
                It would typically call ``items`` or ``sorted_items`` method on
                the argument depending on whether sorted output is desired.

        Yields:
            ``(path, value)`` tuples.
        """
        # Use iterative function with stack on the heap so we don't hit Python's
        # recursion depth limits.
        node = self
        stack: list[Iterator[tuple[str, _Node[V]]]] = []
        while True:
            if node.value is not _SentinelClass._Sentinel:
                yield path, node.value

            if (not shallow or node.value is _SentinelClass._Sentinel) and node.children:
                stack.append(iter(items(node.children)))
                path.append("")

            while True:
                try:
                    step, node = next(stack[-1])
                    path[-1] = step
                    break
                except StopIteration:
                    stack.pop()
                    path.pop()
                except IndexError:
                    return

    def traverse(
        self,
        node_factory: NodeFactory[V],
        path_conv: PathConv,
        path: list[str],
        items: T_Iteritems[V],
    ):
        """Traverses the node and returns another type of node from factory.

        Args:
            node_factory: Callable to construct return value.
            path_conv: Callable to convert node path to a key.
            path: Current path for this node.
            items: A callable which takes ``node.children`` as a sole argument
                and returns an iterable of children as ``(step, node)`` pairs.
                It would typically call ``items`` or ``sorted_items`` method on
                the argument depending on whether sorted output is desired.

        Returns:
            An object constructed by calling node_factory(path_conv, path,
            children, value=...), where children are constructed by node_factory
            from the children of this node.  There doesn't need to be 1:1
            correspondence between original nodes in the trie and constructed
            nodes (see make_test_node_and_compress in test.py).
        """
        children = (node.traverse(node_factory, path_conv, path + [step], items) for step, node in items(self.children))

        value_maybe = None
        if self.value is not _SentinelClass._Sentinel:
            value_maybe = self.value

        return node_factory(path_conv, tuple(path), children, value_maybe)

    def equals(self, other: _Node[V]):
        """Returns whether this and other node are recursively equal."""
        # Like iterate, we don't recurse so this works on deep tries.
        if not isinstance(other, _Node):
            return False
        a, b = self, other
        stack = []
        while True:
            if a.value != b.value or len(a.children) != len(b.children):
                return False
            if len(a.children) == 1:
                # We know a.children and b.children are both _OneChild objects
                # but pylint doesn’t recognise that: pylint: disable=no-member
                if TYPE_CHECKING:
                    assert isinstance(a.children, _OneChild)
                    assert isinstance(b.children, _OneChild)
                if a.children.step != b.children.step:
                    return False
                a = a.children.node
                b = b.children.node
                continue
            if a.children:
                stack.append((iter(a.children.items()), b.children))

            while True:
                try:
                    key, a = next(stack[-1][0])
                    b = stack[-1][1][key]
                    break
                except StopIteration:
                    stack.pop()
                except IndexError:
                    return True
                except KeyError:
                    return False

    def __bool__(self):
        raise NotImplementedError()

    def __hash__(self):
        raise NotImplementedError()

    def shallow_copy(self, make_copy: T_Copy) -> _Node[V]:
        """Returns a copy of the node which shares the children property."""
        cpy = _Node()
        cpy.children = self.children
        cpy.value = make_copy(self.value)
        return cpy

    def copy(self, make_copy: T_Copy) -> _Node[V]:
        """Returns a copy of the node structure."""
        cpy = self.shallow_copy(make_copy)
        queue = [(cpy,)]
        while queue:
            for node in queue.pop():
                node.children = node.children.copy(make_copy, queue)
        return cpy

    def __getstate__(self):
        """Get state used for pickling.

        The state is encoded as a list of simple commands which consist of an
        integer and some command-dependent number of arguments.  The commands
        modify what the current node is by navigating the trie up and down and
        setting node values.  Possible commands are:

        * [n, step0, step1, ..., stepn-1, value], for n >= 0, specifies step
          needed to reach the next current node as well as its new value.  There
          is no way to create a child node without setting its (or its
          descendant's) value.

        * [-n], for -n < 0, specifies to go up n steps in the trie.

        When encoded as a state, the commands are flattened into a single list.

        For example::

            [ 0, 'Root',
              2, 'Foo', 'Bar', 'Root/Foo/Bar Node',
             -1,
              1, 'Baz', 'Root/Foo/Baz Node',
             -2,
              1, 'Qux', 'Root/Qux Node' ]

        Creates the following hierarchy::

            -* value: Root
             +-- Foo --* no value
             |         +-- Bar -- * value: Root/Foo/Bar Node
             |         +-- Baz -- * value: Root/Foo/Baz Node
             +-- Qux -- * value: Root/Qux Node

        Returns:
            A pickable state which can be passed to :func:`_Node.__setstate__`
            to reconstruct the node and its full hierarchy.
        """
        # Like iterate, we don't recurse so pickling works on deep tries.
        state: list = [] if self.value is _SentinelClass._Sentinel else [0]
        last_cmd = 0
        node = self
        stack = []
        while True:
            if node.value is not _SentinelClass._Sentinel:
                last_cmd = 0
                state.append(node.value)
            stack.append(iter(node.children.items()))

            while True:
                step, node = next(stack[-1], (None, None))
                if node is not None:
                    break

                if last_cmd < 0:
                    state[-1] -= 1
                else:
                    last_cmd = -1
                    state.append(-1)
                stack.pop()
                if not stack:
                    state.pop()  # Final -n command is not necessary
                    return state

            if last_cmd > 0:
                last_cmd += 1
                state[-last_cmd] += 1
            else:
                last_cmd = 1
                state.append(1)
            state.append(step)

    def __setstate__(self, state):
        """Unpickles node.  See :func:`_Node.__getstate__`."""
        self.__init__()
        state = iter(state)
        stack: list[_Node[V]] = [self]
        for cmd in state:
            if cmd < 0:
                del stack[cmd:]
            else:
                while cmd > 0:
                    parent = stack[-1]
                    stack.append(parent.children.add(parent, next(state)))
                    cmd -= 1
                stack[-1].value = next(state)


_KT = TypeVar("_KT", covariant=True)


class Step(Protocol[_KT, _VT]):
    def __bool__(self) -> bool: ...

    @overload
    def get(self) -> _VT | None: ...
    @overload
    def get(self, default: _VT) -> _VT: ...
    def get(self, default: _VT | None = None) -> _VT | None: ...

    def set(self, value: _VT) -> None: ...

    def setdefault(self, value: _VT) -> _VT: ...

    @property
    def is_set(self) -> bool: ...

    @property
    def has_subtrie(self) -> bool: ...

    @property
    def key(self) -> _KT: ...

    @property
    def value(self) -> _VT: ...

    def __repr__(self) -> str: ...


class _NoneStep(Step[None, None]):
    """Representation of a non-existent step towards non-existent node."""

    __slots__ = ()

    def __bool__(self) -> Literal[False]:
        return False

    def get(self, default=None):
        return default

    def set(self, value):
        return

    def setdefault(self, value):
        return value

    is_set = property(__bool__)  # type: ignore
    key = property(lambda self: None)  # type: ignore
    has_subtrie = property(__bool__)  # type: ignore
    value = property(lambda self: None)  # type: ignore

    def __repr__(self):
        return "(None Step)"


class _Step(Step[str, V], Generic[V]):
    """Representation of a single step on a path towards particular node."""

    __slots__ = ("_trie", "_path", "_pos", "_node", "__key")

    def __init__(self, trie: Trie[V], path: Iterable[str], pos: int, node: _Node[V]):
        self._trie = trie
        self._path = path
        self._pos = pos
        self._node = node

    def __bool__(self) -> Literal[True]:
        return True

    @property
    def is_set(self):
        """Returns whether the node has value assigned to it."""
        return self._node.value is not _SentinelClass._Sentinel

    @property
    def has_subtrie(self):
        """Returns whether the node has any children."""
        return bool(self._node.children)

    def get(self, default: V | None = None):  # type: ignore
        """Returns node's value or the default if value is not assigned."""
        v = self._node.value
        return default if v is _SentinelClass._Sentinel else v

    def set(self, value: V):
        """Deprecated.  Use ``step.value = value`` instead."""
        self._node.value = value

    def setdefault(self, value: V) -> V:
        """Assigns value to the node if one is not set then returns it."""
        if self._node.value is _SentinelClass._Sentinel:
            self._node.value = value
        return self._node.value

    def __repr__(self):
        return f"({self.key!r}, {self.value!r})"

    @property
    def key(self) -> str:
        """Returns key of the node."""
        if not hasattr(self, "_Step__key"):
            # pylint:disable=protected-access,attribute-defined-outside-init
            self.__key = self._trie._key_from_path(list(self._path)[: self._pos])
        return self.__key

    @property
    def value(self) -> V:
        """Returns node's value or raises KeyError."""
        v = self._node.value
        if v is _SentinelClass._Sentinel:
            raise ShortKeyError(self.key)
        return v

    @value.setter
    def value(self, value: V):
        self._node.value = value


_NONE_STEP: Final[_NoneStep] = _NoneStep()


class Trie(Generic[V]):
    """A trie implementation with dict interface plus some extensions.

    Keys used with the :class:`tarina.trie.Trie` class must be iterable which each
    component being a hashable objects.  In other words, for a given key,
    ``dict.fromkeys(key)`` must be valid expression.

    In particular, strings work well as trie keys, however when getting them
    back (for example via :func:`Trie.iterkeys` method), instead of strings,
    tuples of characters are produced.  For that reason,
    :class:`tarina.trie.CharTrie` or :class:`tarina.trie.StringTrie` classes may be
    preferred when using string keys.
    """

    def __init__(
        self,
        other: MutableMapping[str, V] | Iterable[tuple[str, V]] | None = None,
        /,
        **kwargs: V,
    ):
        """Initialises the trie.

        Arguments are interpreted the same way :func:`Trie.update` interprets
        them.
        """
        self._root: _Node[V] = _Node()
        self._items_callback = self._ITEMS_CALLBACKS[0]
        self.update(other, **kwargs)

    _ITEMS_CALLBACKS: tuple[T_Iteritems[V], T_Iteritems[V]] = (
        lambda x: x.items(),
        lambda x: x.sorted_items(),
    )

    def enable_sorting(self, enable=True):
        """Enables sorting of child nodes when iterating and traversing.

        Normally, child nodes are not sorted when iterating or traversing over
        the trie (just like dict elements are not sorted).  This method allows
        sorting to be enabled (which was the behaviour prior to tarina.trie 2.0
        release).

        For Trie class, enabling sorting of children is identical to simply
        sorting the list of items since Trie returns keys as tuples.  However,
        for other implementations such as StringTrie the two may behave subtly
        different.  For example, sorting items might produce::

            root/foo-bar
            root/foo/baz

        even though foo comes before foo-bar.

        Args:
            enable: Whether to enable sorting of child nodes.
        """
        self._items_callback = self._ITEMS_CALLBACKS[bool(enable)]

    def __getstate__(self):
        # encode self._items_callback as self._sorted when pickling
        state = self.__dict__.copy()
        callback = state.pop("_items_callback", None)
        state["_sorted"] = callback is self._ITEMS_CALLBACKS[1]
        return state

    def __setstate__(self, state):
        # translate self._sorted back to _items_callback when unpickling
        self.__dict__ = state
        self.enable_sorting(state.pop("_sorted"))

    def clear(self):
        """Removes all the values from the trie."""
        del self._root.children
        self._root = _Node()

    def update(
        self,
        other: MutableMapping[str, V] | Iterable[tuple[str, V]] | None = None,
        /,
        **kwargs: V,
    ):
        """Updates stored values.  Works like :meth:`dict.update`."""
        if other and isinstance(other, MutableMapping):
            for key, value in self.iteritems(other):  # type: ignore
                self[key] = value
            other = ()
        MutableMapping.update(self, other or (), **kwargs)  # type: ignore

    def merge(self, other: Trie[V], overwrite: bool = False):
        """Moves nodes from other trie into this one.

        The merging happens at trie structure level and as such is different
        than iterating over items of one trie and setting them in the other
        trie.

        The merging may happen between different types of tries resulting in
        different (key, value) pairs in the destination trie compared to the
        source.  For example, merging two :class:`tarina.trie.StringTrie` objects
        each using different separators will work as if the other trie had
        separator of this trie.  Similarly, a :class:`tarina.trie.CharTrie` may be
        merged into a :class:`tarina.trie.StringTrie` but when keys are read those
        will be joined by the separator.  For example:

            >>> import tarina.trie
            >>> st = tarina.trie.StringTrie(separator='.')
            >>> st.merge(tarina.trie.StringTrie({'foo/bar': 42}))
            >>> list(st.items())
            [('foo.bar', 42)]
            >>> st.merge(tarina.trie.CharTrie({'baz': 24}))
            >>> sorted(st.items())
            [('b.a.z', 24), ('foo.bar', 42)]

        Not all tries can be merged into other tries.  For example,
        a :class:`tarina.trie.StringTrie` may not be merged into
        a :class:`tarina.trie.CharTrie` because the latter imposes a requirement for
        each component in the key to be exactly one character while in the
        former components may be arbitrary length.

        Note that the other trie is cleared and any references or iterators over
        it are invalidated.  To preserve other’s value it needs to be copied
        first.

        Args:
            other: Other trie to move nodes from.
            overwrite: Whether to overwrite existing values in this trie.
        """
        if not isinstance(other, Trie):
            raise TypeError("Can only merge tries with other tries.")
        if isinstance(self, type(other)):
            self._merge_impl(self, other, overwrite=overwrite)
        else:
            other._merge_impl(self, other, overwrite=overwrite)  # pylint: disable=protected-access
        other.clear()

    @classmethod
    def _merge_impl(cls, dst, src, overwrite):
        # pylint: disable=protected-access
        dst._root.merge(src._root, overwrite=overwrite)

    def copy(self, __make_copy: T_Copy = lambda x: x):
        """Returns a shallow copy of the object."""
        # pylint: disable=protected-access
        cpy = self.__class__()
        cpy.__dict__ = self.__dict__.copy()
        cpy._root = self._root.copy(__make_copy)
        return cpy

    def __copy__(self):
        return self.copy()

    def __deepcopy__(self, memo):
        return self.copy(lambda x: _copy.deepcopy(x, memo))

    @classmethod
    @overload
    def fromkeys(cls, keys: Iterable[str], value: None = None) -> Trie[Any | None]: ...
    @classmethod
    @overload
    def fromkeys(cls, keys: Iterable[str], value: V1) -> Trie[V1]: ...
    @classmethod
    def fromkeys(cls, keys: Iterable[str], value: Any = None) -> Trie[Any]:
        """Creates a new trie with given keys set.

        This is roughly equivalent to calling the constructor with a ``(key,
        value) for key in keys`` generator.

        Args:
            keys: An iterable of keys that should be set in the new trie.
            value: Value to associate with given keys.

        Returns:
            A new trie where each key from ``keys`` has been set to the given
            value.
        """
        trie = cls()
        for key in keys:
            trie[key] = value
        return trie

    def _get_node(
        self, key: str | Literal[_SentinelClass._Sentinel]
    ) -> tuple[_Node[V], list[tuple[None, _Node[V]] | tuple[str, _Node[V]]]]:
        """Returns node for given key.  Creates it if requested.

        Args:
            key: A key to look for.

        Returns:
            ``(node, trace)`` tuple where ``node`` is the node for given key and
            ``trace`` is a list specifying path to reach the node including all
            the encountered nodes.  Each element of trace is a ``(step, node)``
            tuple where ``step`` is a step from parent node to given node and
            ``node`` is node on the path.  The first element of the path is
            always ``(None, self._root)``.

        Raises:
            KeyError: If there is no node for the key.
        """
        node: _Node[V] = self._root
        trace: list[tuple[None, _Node[V]] | tuple[str, _Node[V]]] = [(None, node)]
        for step in self.__path_from_key(key):
            # pylint thinks node.children is always _NoChildren and thus that
            # we’re assigning None here; pylint: disable=assignment-from-none
            if (_node := node.children.get(step)) is None:
                raise KeyError(key)
            node = _node
            trace.append((step, node))
        return node, trace

    def _set_node(self, key: str, value: V, only_if_missing: bool = False) -> _Node[V]:
        """Sets value for a given key.

        Args:
            key: Key to set value of.
            value: Value to set to.
            only_if_missing: If true, value won't be changed if the key is
                    already associated with a value.

        Returns:
            The node.
        """
        node = self._root
        for step in self.__path_from_key(key):
            node = node.children.require(node, step)
        if node.value is _SentinelClass._Sentinel or not only_if_missing:
            node.value = value
        return node

    def _set_node_if_no_prefix(self: Trie[bool], key: str):
        """Sets given key to True but only if none of its prefixes are present.

        If value is set, removes all ancestors of the node.

        This is a method for exclusive use by PrefixSet.

        Args:
            key: Key to set value of.
        """
        steps = iter(self.__path_from_key(key))
        node = self._root
        try:
            while node.value is _SentinelClass._Sentinel:
                node = node.children.require(node, next(steps))
        except StopIteration:
            node.value = True
            node.children = _EMPTY

    def __iter__(self):
        return self.iterkeys()

    # pylint: disable=arguments-differ

    def iteritems(
        self, prefix: str | Literal[_SentinelClass._Sentinel] = _SentinelClass._Sentinel, shallow: bool = False
    ) -> Generator[tuple[str, V], Any, None]:
        """Yields all nodes with associated values with given prefix.

        Only nodes with values are output.  For example::

            >>> import tarina.trie
            >>> t = tarina.trie.StringTrie()
            >>> t['foo'] = 'Foo'
            >>> t['foo/bar/baz'] = 'Baz'
            >>> t['qux'] = 'Qux'
            >>> sorted(t.items())
            [('foo', 'Foo'), ('foo/bar/baz', 'Baz'), ('qux', 'Qux')]

        Items are generated in topological order (i.e. parents before child
        nodes) but the order of siblings is unspecified.  At an expense of
        efficiency, :func:`Trie.enable_sorting` method can turn deterministic
        ordering of siblings.

        With ``prefix`` argument, only items with specified prefix are generated
        (i.e. only given subtrie is traversed) as demonstrated by::

            >>> t.items(prefix='foo')
            [('foo', 'Foo'), ('foo/bar/baz', 'Baz')]

        With ``shallow`` argument, if a node has value associated with it, it's
        children are not traversed even if they exist which can be seen in::

            >>> sorted(t.items(shallow=True))
            [('foo', 'Foo'), ('qux', 'Qux')]

        Args:
            prefix: Prefix to limit iteration to.
            shallow: Perform a shallow traversal, i.e. do not yield items if
                their prefix has been yielded.

        Yields:
            ``(key, value)`` tuples.

        Raises:
            KeyError: If ``prefix`` does not match any node.
        """
        node, _ = self._get_node(prefix)
        for path, value in node.iterate(list(self.__path_from_key(prefix)), shallow, self._items_callback):
            yield (self._key_from_path(path), value)

    def iterkeys(
        self, prefix: str | Literal[_SentinelClass._Sentinel] = _SentinelClass._Sentinel, shallow: bool = False
    ):
        """Yields all keys having associated values with given prefix.

        This is equivalent to taking first element of tuples generated by
        :func:`Trie.iteritems` which see for more detailed documentation.

        Args:
            prefix: Prefix to limit iteration to.
            shallow: Perform a shallow traversal, i.e. do not yield keys if
                their prefix has been yielded.

        Yields:
            All the keys (with given prefix) with associated values in the trie.

        Raises:
            KeyError: If ``prefix`` does not match any node.
        """
        for key, _ in self.iteritems(prefix=prefix, shallow=shallow):
            yield key

    def itervalues(
        self, prefix: str | Literal[_SentinelClass._Sentinel] = _SentinelClass._Sentinel, shallow: bool = False
    ):
        """Yields all values associated with keys with given prefix.

        This is equivalent to taking second element of tuples generated by
        :func:`Trie.iteritems` which see for more detailed documentation.

        Args:
            prefix: Prefix to limit iteration to.
            shallow: Perform a shallow traversal, i.e. do not yield values if
                their prefix has been yielded.

        Yields:
            All the values associated with keys (with given prefix) in the trie.

        Raises:
            KeyError: If ``prefix`` does not match any node.
        """
        node, _ = self._get_node(prefix)
        for _, value in node.iterate(list(self.__path_from_key(prefix)), shallow, self._items_callback):
            yield value

    def items(self, prefix: str | Literal[_SentinelClass._Sentinel] = _SentinelClass._Sentinel, shallow: bool = False):
        """Returns a list of ``(key, value)`` pairs in given subtrie.

        This is equivalent to constructing a list from generator returned by
        :func:`Trie.iteritems` which see for more detailed documentation.
        """
        return list(self.iteritems(prefix=prefix, shallow=shallow))

    def keys(self, prefix: str | Literal[_SentinelClass._Sentinel] = _SentinelClass._Sentinel, shallow: bool = False):
        """Returns a list of all the keys, with given prefix, in the trie.

        This is equivalent to constructing a list from generator returned by
        :func:`Trie.iterkeys` which see for more detailed documentation.
        """
        return list(self.iterkeys(prefix=prefix, shallow=shallow))

    def values(self, prefix: str | Literal[_SentinelClass._Sentinel] = _SentinelClass._Sentinel, shallow: bool = False):
        """Returns a list of values in given subtrie.

        This is equivalent to constructing a list from generator returned by
        :func:`Trie.itervalues` which see for more detailed documentation.
        """
        return list(self.itervalues(prefix=prefix, shallow=shallow))

    def __len__(self):
        """Returns number of values in a trie.

        Note that this method is expensive as it iterates over the whole trie.
        """
        return sum(1 for _ in self.itervalues())

    def __bool__(self):
        return self._root.value is not _SentinelClass._Sentinel or bool(self._root.children)

    __hash__ = None  # type: ignore

    HAS_VALUE = 1
    HAS_SUBTRIE = 2

    def has_node(self, key: str):
        """Returns whether given node is in the trie.

        Return value is a bitwise or of ``HAS_VALUE`` and ``HAS_SUBTRIE``
        constants indicating node has a value associated with it and that it is
        a prefix of another existing key respectively.  Both of those are
        independent of each other and all of the four combinations are possible.
        For example::

            >>> import tarina.trie
            >>> t = tarina.trie.StringTrie()
            >>> t['foo/bar'] = 'Bar'
            >>> t['foo/bar/baz'] = 'Baz'
            >>> t.has_node('qux') == 0
            True
            >>> t.has_node('foo/bar/baz') == tarina.trie.Trie.HAS_VALUE
            True
            >>> t.has_node('foo') == tarina.trie.Trie.HAS_SUBTRIE
            True
            >>> t.has_node('foo/bar') == (tarina.trie.Trie.HAS_VALUE |
            ...                           tarina.trie.Trie.HAS_SUBTRIE)
            True

        There are two higher level methods built on top of this one which give
        easier interface for the information. :func:`Trie.has_key` returns
        whether node has a value associated with it and :func:`Trie.has_subtrie`
        checks whether node is a prefix.  Continuing previous example::

            >>> t.has_key('qux'), t.has_subtrie('qux')
            (False, False)
            >>> t.has_key('foo/bar/baz'), t.has_subtrie('foo/bar/baz')
            (True, False)
            >>> t.has_key('foo'), t.has_subtrie('foo')
            (False, True)
            >>> t.has_key('foo/bar'), t.has_subtrie('foo/bar')
            (True, True)

        Args:
            key: A key to look for.

        Returns:
            Non-zero if node exists and if it does a bit-field denoting whether
            it has a value associated with it and whether it has a subtrie.
        """
        try:
            node, _ = self._get_node(key)
        except KeyError:
            return 0
        return (self.HAS_VALUE * (node.value is not _SentinelClass._Sentinel)) | (
            self.HAS_SUBTRIE * bool(node.children)
        )

    def has_key(self, key: str):
        """Indicates whether given key has value associated with it.

        See :func:`Trie.has_node` for more detailed documentation.
        """
        return bool(self.has_node(key) & self.HAS_VALUE)

    def has_subtrie(self, key: str):
        """Returns whether given key is a prefix of another key in the trie.

        See :func:`Trie.has_node` for more detailed documentation.
        """
        return bool(self.has_node(key) & self.HAS_SUBTRIE)

    @staticmethod
    @overload
    def _slice_maybe(key_or_slice: str) -> tuple[str, Literal[False]]: ...
    @staticmethod
    @overload
    def _slice_maybe(key_or_slice: slice) -> tuple[str, Literal[True]]: ...
    @staticmethod
    def _slice_maybe(key_or_slice):
        """Checks whether argument is a slice or a plain key.

        Args:
            key_or_slice: A key or a slice to test.

        Returns:
            ``(key, is_slice)`` tuple.  ``is_slice`` indicates whether
            ``key_or_slice`` is a slice and ``key`` is either ``key_or_slice``
            itself (if it's not a slice) or slice's start position.

        Raises:
            TypeError: If ``key_or_slice`` is a slice whose stop or step are not
                ``None`` In other words, only ``[key:]`` slices are valid.
        """
        if isinstance(key_or_slice, slice):
            if key_or_slice.stop is not None or key_or_slice.step is not None:
                raise TypeError(key_or_slice)
            return key_or_slice.start, True
        return key_or_slice, False

    @overload
    def __getitem__(self, key_or_slice: str) -> V: ...

    @overload
    def __getitem__(self, key_or_slice: slice) -> Generator[V, Any, None]: ...
    def __getitem__(self, key_or_slice: str | slice):
        """Returns value associated with given key or raises KeyError.

        When argument is a single key, value for that key is returned (or
        :class:`KeyError` exception is thrown if the node does not exist or has
        no value associated with it).

        When argument is a slice, it must be one with only `start` set in which
        case the access is identical to :func:`Trie.itervalues` invocation with
        prefix argument.

        Example:

            >>> import tarina.trie
            >>> t = tarina.trie.StringTrie()
            >>> t['foo/bar'] = 'Bar'
            >>> t['foo/baz'] = 'Baz'
            >>> t['qux'] = 'Qux'
            >>> t['foo/bar']
            'Bar'
            >>> sorted(t['foo':])
            ['Bar', 'Baz']
            >>> t['foo']  # doctest: +IGNORE_EXCEPTION_DETAIL
            Traceback (most recent call last):
                ...
            ShortKeyError: 'foo'

        Args:
            key_or_slice: A key or a slice to look for.

        Returns:
            If a single key is passed, a value associated with given key.  If
            a slice is passed, a generator of values in specified subtrie.

        Raises:
            ShortKeyError: If the key has no value associated with it but is
                a prefix of some key with a value.  Note that
                :class:`ShortKeyError` is subclass of :class:`KeyError`.
            KeyError: If key has no value associated with it nor is a prefix of
                an existing key.
            TypeError: If ``key_or_slice`` is a slice but it's stop or step are
                not ``None``.
        """
        start, is_slice = self._slice_maybe(key_or_slice)
        if is_slice:
            return self.itervalues(start)
        if TYPE_CHECKING:
            assert isinstance(key_or_slice, str)
        node, _ = self._get_node(key_or_slice)
        if node.value is _SentinelClass._Sentinel:
            raise ShortKeyError(key_or_slice)
        return node.value

    def __setitem__(self, key_or_slice: str | slice, value: V):
        """Sets value associated with given key.

        If `key_or_slice` is a key, simply associate it with given value.  If it
        is a slice (which must have `start` set only), it in addition clears any
        subtrie that might have been attached to particular key.  For example::

            >>> import tarina.trie
            >>> t = tarina.trie.StringTrie()
            >>> t['foo/bar'] = 'Bar'
            >>> t['foo/baz'] = 'Baz'
            >>> sorted(t.keys())
            ['foo/bar', 'foo/baz']
            >>> t['foo':] = 'Foo'
            >>> t.keys()
            ['foo']

        Args:
            key_or_slice: A key to look for or a slice.  If it is a slice, the
                whole subtrie (if present) will be replaced by a single node
                with given value set.
            value: Value to set.

        Raises:
            TypeError: If key is a slice whose stop or step are not None.
        """
        key, is_slice = self._slice_maybe(key_or_slice)
        node = self._set_node(key, value)
        if is_slice:
            node.children = _EMPTY

    @overload
    def setdefault(self: Trie[V1 | None], key: str, default: None = None) -> V1 | None: ...
    @overload
    def setdefault(self, key: str, default: V) -> V: ...
    def setdefault(self, key: str, default: V | None = None):  # type: ignore
        """Sets value of a given node if not set already.  Also returns it.

        In contrast to :func:`Trie.__setitem__`, this method does not accept
        slice as a key.
        """
        return self._set_node(key, default, only_if_missing=True).value  # type: ignore

    @staticmethod
    def _pop_value(trace: list[tuple[None, _Node[V]] | tuple[str, _Node[V]]]):
        """Removes value from given node and removes any empty nodes.

        Args:
            trace: Trace to the node to cleanup as returned by
                :func:`Trie._get_node`.  The last element of the trace denotes
                the node to get value of.

        Returns:
            Value which was held in the node at the end of specified trace.
            This may be _EMPTY if the node didn’t have a value in the first
            place.
        """
        i = len(trace) - 1  # len(path) >= 1 since root is always there
        _trace: list[tuple[str, _Node[V]]] = trace  # type: ignore
        step, node = _trace[i]
        value, node.value = node.value, _SentinelClass._Sentinel
        while i and node.value is _SentinelClass._Sentinel and not node.children:
            i -= 1
            parent_step, parent = _trace[i]
            parent.children.delete(parent, step)
            step, node = parent_step, parent
        return value

    def pop(self, key: str, default: V | Literal[_SentinelClass._Sentinel] = _SentinelClass._Sentinel) -> V:
        """Deletes value associated with given key and returns it.

        Args:
            key: A key to look for.
            default: If specified, value that will be returned if given key has
                no value associated with it.  If not specified, method will
                throw KeyError in such cases.

        Returns:
            Removed value, if key had value associated with it, or ``default``
            (if given).

        Raises:
            ShortKeyError: If ``default`` has not been specified and the key has
                no value associated with it but is a prefix of some key with
                a value.  Note that :class:`ShortKeyError` is subclass of
                :class:`KeyError`.
            KeyError: If default has not been specified and key has no value
                associated with it nor is a prefix of an existing key.
        """
        try:
            _, trace = self._get_node(key)
        except KeyError:
            if default is not _SentinelClass._Sentinel:
                return default
            raise
        value = self._pop_value(trace)
        if value is not _SentinelClass._Sentinel:
            return value
        if default is not _SentinelClass._Sentinel:
            return default
        raise ShortKeyError()

    def popitem(self) -> tuple[str, V | Literal[_SentinelClass._Sentinel]]:
        """Deletes an arbitrary value from the trie and returns it.

        There is no guarantee as to which item is deleted and returned.  Neither
        in respect to its lexicographical nor topological order.

        Returns:
            ``(key, value)`` tuple indicating deleted key.

        Raises:
            KeyError: If the trie is empty.
        """
        if not self:
            raise KeyError()
        node = self._root
        trace: list[tuple[None, _Node[V]] | tuple[str, _Node[V]]] = [(None, node)]
        while node.value is _SentinelClass._Sentinel:
            step, node = node.children.pick()
            trace.append((step, node))
        _trace: list[tuple[str, _Node[V]]] = trace[1:]  # type: ignore
        key = self._key_from_path((step for step, _ in _trace))
        return key, self._pop_value(trace)

    def __delitem__(self, key_or_slice: str | slice):
        """Deletes value associated with given key or raises KeyError.

        If argument is a key, value associated with it is deleted.  If the key
        is also a prefix, its descendents are not affected.  On the other hand,
        if the argument is a slice (in which case it must have only start set),
        the whole subtrie is removed.  For example::

            >>> import tarina.trie
            >>> t = tarina.trie.StringTrie()
            >>> t['foo'] = 'Foo'
            >>> t['foo/bar'] = 'Bar'
            >>> t['foo/bar/baz'] = 'Baz'
            >>> del t['foo/bar']
            >>> t.keys()
            ['foo', 'foo/bar/baz']
            >>> del t['foo':]
            >>> t.keys()
            []

        Args:
            key_or_slice: A key to look for or a slice.  If key is a slice, the
                    whole subtrie will be removed.

        Raises:
            ShortKeyError: If the key has no value associated with it but is
                a prefix of some key with a value.  This is not thrown if
                key_or_slice is a slice -- in such cases, the whole subtrie is
                removed.  Note that :class:`ShortKeyError` is subclass of
                :class:`KeyError`.
            KeyError: If key has no value associated with it nor is a prefix of
                an existing key.
            TypeError: If key is a slice whose stop or step are not ``None``.
        """
        key, is_slice = self._slice_maybe(key_or_slice)
        node, trace = self._get_node(key)
        if is_slice:
            node.children = _EMPTY
        elif node.value is _SentinelClass._Sentinel:
            raise ShortKeyError(key)
        self._pop_value(trace)

    def walk_towards(self, key: str) -> Generator[_Step[V], Any, None]:
        """Yields nodes on the path to given node.

        Args:
            key: Key of the node to look for.

        Yields:
            :class:`tarina.trie.Trie._Step` objects which can be used to extract or
            set node's value as well as get node's key.

            When representing nodes with assigned values, the objects can be
            treated as ``(k, value)`` pairs denoting keys with associated values
            encountered on the way towards the specified key.  This is
            deprecated, prefer using ``key`` and ``value`` properties or ``get``
            method of the object.

        Raises:
            KeyError: If node with given key does not exist.  It's all right if
                they value is not assigned to the node provided it has a child
                node.  Because the method is a generator, the exception is
                raised only once a missing node is encountered.
        """
        node = self._root
        path = list(self.__path_from_key(key))
        pos = 0
        while True:
            yield _Step(self, path, pos, node)
            if pos == len(path):
                break
            # pylint thinks node.children is always _NoChildren and thus that
            # we’re assigning None here; pylint: disable=assignment-from-none
            node = node.children.get(path[pos])
            if node is None:
                raise KeyError(key)
            pos += 1

    def prefixes(self, key) -> Generator[_Step[V], Any, None]:
        """Walks towards the node specified by key and yields all found items.

        Example:

            >>> import tarina.trie
            >>> t = tarina.trie.StringTrie()
            >>> t['foo'] = 'Foo'
            >>> t['foo/bar/baz'] = 'Baz'
            >>> list(t.prefixes('foo/bar/baz/qux'))
            [('foo': 'Foo'), ('foo/bar/baz': 'Baz')]
            >>> list(t.prefixes('does/not/exist'))
            []

        Args:
            key: Key to look for.

        Yields:
            :class:`tarina.trie.Trie._Step` objects which can be used to extract or
            set node's value as well as get node's key.

            The objects can be treated as ``(k, value)`` pairs denoting keys
            with associated values encountered on the way towards the specified
            key.  This is deprecated, prefer using ``key`` and ``value``
            properties of the object.
        """
        try:
            for step in self.walk_towards(key):
                if step.is_set:
                    yield step
        except KeyError:
            pass

    def shortest_prefix(self, key) -> _Step[V] | _NoneStep:
        """Finds the shortest prefix of a key with a value.

        This is roughly equivalent to taking the first object yielded by
        :func:`Trie.prefixes` with additional handling for situations when no
        prefixes are found.

        Example:

            >>> import tarina.trie
            >>> t = tarina.trie.StringTrie()
            >>> t['foo'] = 'Foo'
            >>> t['foo/bar/baz'] = 'Baz'
            >>> t.shortest_prefix('foo/bar/baz/qux')
            ('foo': 'Foo')
            >>> t.shortest_prefix('foo/bar/baz/qux').key
            'foo'
            >>> t.shortest_prefix('foo/bar/baz/qux').value
            'Foo'
            >>> t.shortest_prefix('does/not/exist')
            (None Step)
            >>> bool(t.shortest_prefix('does/not/exist'))
            False

        Args:
            key: Key to look for.

        Returns:
            :class:`tarina.trie.Trie._Step` object (which can be used to extract or
            set node's value as well as get node's key), or
            a :class:`tarina.trie.Trie._NoneStep` object (which is falsy value
            simulating a _Step with ``None`` key and value) if no prefix is
            found.

            The object can be treated as ``(key, value)`` pair denoting key with
            associated value of the prefix.  This is deprecated, prefer using
            ``key`` and ``value`` properties of the object.
        """
        return next(self.prefixes(key), _NONE_STEP)

    def longest_prefix(self, key) -> _NoneStep | _Step[V]:
        """Finds the longest prefix of a key with a value.

        This is roughly equivalent to taking the last object yielded by
        :func:`Trie.prefixes` with additional handling for situations when no
        prefixes are found.

        Example:

            >>> import tarina.trie
            >>> t = tarina.trie.StringTrie()
            >>> t['foo'] = 'Foo'
            >>> t['foo/bar/baz'] = 'Baz'
            >>> t.longest_prefix('foo/bar/baz/qux')
            ('foo/bar/baz': 'Baz')
            >>> t.longest_prefix('foo/bar/baz/qux').key
            'foo/bar/baz'
            >>> t.longest_prefix('foo/bar/baz/qux').value
            'Baz'
            >>> t.longest_prefix('does/not/exist')
            (None Step)
            >>> bool(t.longest_prefix('does/not/exist'))
            False

        Args:
            key: Key to look for.

        Returns:
            :class:`tarina.trie.Trie._Step` object (which can be used to extract or
            set node's value as well as get node's key), or
            a :class:`tarina.trie.Trie._NoneStep` object (which is falsy value
            simulating a _Step with ``None`` key and value) if no prefix is
            found.

            The object can be treated as ``(key, value)`` pair denoting key with
            associated value of the prefix.  This is deprecated, prefer using
            ``key`` and ``value`` properties of the object.
        """
        ret = _NONE_STEP
        for ret in self.prefixes(key):
            pass
        return ret

    def strictly_equals(self, other):
        """Checks whether tries are equal with the same structure.

        This is stricter comparison than the one performed by equality operator.
        It not only requires for keys and values to be equal but also for the
        two tries to be of the same type and have the same structure.

        For example, for two :class:`tarina.trie.StringTrie` objects to be equal,
        they need to have the same structure as well as the same separator as
        seen below:

            >>> import tarina.trie
            >>> t0 = StringTrie({'foo/bar': 42}, separator='/')
            >>> t1 = StringTrie({'foo.bar': 42}, separator='.')
            >>> t0.strictly_equals(t1)
            False

            >>> t0 = StringTrie({'foo/bar.baz': 42}, separator='/')
            >>> t1 = StringTrie({'foo/bar.baz': 42}, separator='.')
            >>> t0 == t1
            True
            >>> t0.strictly_equals(t1)
            False

        Args:
            other: Other trie to compare to.

        Returns:
            Whether the two tries are the same type and have the same structure.
        """
        if self is other:
            return True
        if type(self) is not type(other):
            return False
        result = self._eq_impl(other)
        if result is NotImplemented:
            return False
        else:
            return result

    def __eq__(self, other):
        """Compares this trie’s mapping with another mapping.

        Note that this method doesn’t take trie’s structure into consideration.
        What matters is whether keys and values in both mappings are the same.
        This may lead to unexpected results, for example:

            >>> import tarina.trie
            >>> t0 = StringTrie({'foo/bar': 42}, separator='/')
            >>> t1 = StringTrie({'foo.bar': 42}, separator='.')
            >>> t0 == t1
            False

            >>> t0 = StringTrie({'foo/bar.baz': 42}, separator='/')
            >>> t1 = StringTrie({'foo/bar.baz': 42}, separator='.')
            >>> t0 == t1
            True

            >>> t0 = Trie({'foo': 42})
            >>> t1 = CharTrie({'foo': 42})
            >>> t0 == t1
            False

        This behaviour is required to maintain consistency with Mapping
        interface and its __eq__ method.  For example, this implementation
        maintains transitivity of the comparison:

            >>> t0 = StringTrie({'foo/bar.baz': 42}, separator='/')
            >>> d = {'foo/bar.baz': 42}
            >>> t1 = StringTrie({'foo/bar.baz': 42}, separator='.')
            >>> t0 == d
            True
            >>> d == t1
            True
            >>> t0 == t1
            True

            >>> t0 = Trie({'foo': 42})
            >>> d = {'foo': 42}
            >>> t1 = CharTrie({'foo': 42})
            >>> t0 == d
            False
            >>> d == t1
            True
            >>> t0 == t1
            False

        Args:
            other: Other object to compare to.

        Returns:
            ``NotImplemented`` if this method does not know how to perform the
            comparison or a ``bool`` denoting whether the two objects are equal
            or not.
        """
        if self is other:
            return True
        if type(other) is type(self):
            result = self._eq_impl(other)
            if result is not NotImplemented:
                return result
        return super().__eq__(other)

    def _eq_impl(self, other: Trie[V]):
        return self._root.equals(other._root)  # pylint: disable=protected-access

    def __ne__(self, other):
        return not self == other

    def _str_items(self, fmt="{k}: {v}"):
        return ", ".join(fmt.format(k=item[0], v=item[1]) for item in self.iteritems())

    def __str__(self):
        return f"{self.__class__.__name__}({self._str_items()})"

    def __repr__(self):
        return f"{self.__class__.__name__}([{self._str_items('({k!r}: {v!r})')}])"

    def __path_from_key(self, key: str | Literal[_SentinelClass._Sentinel]) -> Iterable[str]:
        """Converts a user visible key object to internal path representation.

        Args:
            key: User supplied key or ``_SentinelClass._Sentinel``.

        Returns:
            An empty tuple if ``key`` was ``_SentinelClass._Sentinel``, otherwise whatever
            :func:`Trie._path_from_key` returns.

        Raises:
            TypeError: If ``key`` is of invalid type.
        """
        return () if key is _SentinelClass._Sentinel else self._path_from_key(key)

    def _path_from_key(self, key: str) -> Iterable[str]:
        """Converts a user visible key object to internal path representation.

        The default implementation simply returns key.

        Args:
            key: User supplied key.

        Returns:
            A path, which is an iterable of steps.  Each step must be hashable.

        Raises:
            TypeError: If key is of invalid type.
        """
        return key

    def _key_from_path(self, path: Iterable[str]) -> str:
        """Converts an internal path into a user visible key object.

        The default implementation creates a tuple from the path.

        Args:
            path: Internal path representation.
        Returns:
            A user visible key object.
        """
        return "".join(path)

    def traverse(
        self,
        node_factory: NodeFactory[V],
        prefix: str | Literal[_SentinelClass._Sentinel] = _SentinelClass._Sentinel,
    ):
        """Traverses the tree using node_factory object.

        node_factory is a callable which accepts (path_conv, path, children,
        value=...) arguments, where path_conv is a lambda converting path
        representation to key, path is the path to this node, children is an
        iterable of children nodes constructed by node_factory, optional value
        is the value associated with the path.

        node_factory's children argument is a lazy iterable which has a few
        consequences:

        * To traverse into node's children, the object must be iterated over.
          This can by accomplished by a simple ``children = list(children)``
          statement.
        * Ignoring the argument allows node_factory to stop the traversal from
          going into the children of the node.  In other words, whole subtries
          can be removed from traversal if node_factory chooses so.
        * If children is stored as is (i.e. as a iterator) when it is iterated
          over later on it may see an inconsistent state of the trie if it has
          changed between invocation of this method and the iteration.

        However, to allow constant-time determination whether the node has
        children or not, the iterator implements bool conversion such that
        ``has_children = bool(children)`` will tell whether node has children
        without iterating over them.  (Note that ``bool(children)`` will
        continue returning ``True`` even if the iterator has been iterated
        over).

        :func:`Trie.traverse` has two advantages over :func:`Trie.iteritems` and
        similar methods:

        1. it allows subtries to be skipped completely when going through the
           list of nodes based on the property of the parent node; and

        2. it represents structure of the trie directly making it easy to
           convert structure into a different representation.

        For example, the below snippet prints all files in current directory
        counting how many HTML files were found but ignores hidden files and
        directories (i.e. those whose names start with a dot)::

            import os
            import tarina.trie

            t = tarina.trie.StringTrie(separator=os.sep)

            # Construct a trie with all files in current directory and all
            # of its sub-directories.  Files get set a True value.
            # Directories are represented implicitly by being prefixes of
            # files.
            for root, _, files in os.walk('.'):
                for name in files: t[os.path.join(root, name)] = True

            def traverse_callback(path_conv, path, children, is_file=False):
                if path and path[-1] != '.' and path[-1][0] == '.':
                    # Ignore hidden directory (but accept root node and '.')
                    return 0
                elif is_file:
                    print path_conv(path)
                    return int(path[-1].endswith('.html'))
                else:
                    # Otherwise, it's a directory.  Traverse into children.
                    return sum(children)

            print t.traverse(traverse_callback)

        As documented, ignoring the children argument causes subtrie to be
        omitted and not walked into.

        In the next example, the trie is converted to a tree representation
        where child nodes include a pointer to their parent.  As before, hidden
        files and directories are ignored::

            import os
            import tarina.trie

            t = tarina.trie.StringTrie(separator=os.sep)
            for root, _, files in os.walk('.'):
                for name in files: t[os.path.join(root, name)] = True

            class File:
                def __init__(self, name):
                    self.name = name
                    self.parent = None

            class Directory(File):
                def __init__(self, name, children):
                    super().__init__(name)
                    self._children = children
                    for child in children:
                        child.parent = self

            def traverse_callback(path_conv, path, children, is_file=False):
                if not path or path[-1] == '.' or path[-1][0] != '.':
                    if is_file:
                        return File(path[-1])
                    children = filter(None, children)
                    return Directory(path[-1] if path else '', children)

            root = t.traverse(traverse_callback)

        Note: Unlike iterators, when used on a deep trie, traverse method is
        prone to rising a RuntimeError exception when Python's maximum recursion
        depth is reached.  This can be addressed by not iterating over children
        inside of the node_factory.  For example, the below code converts a trie
        into an undirected graph using adjacency list representation::

            def undirected_graph_from_trie(t):
                '''Converts trie into a graph and returns its nodes.'''

                Node = collections.namedtuple('Node', 'path neighbours')

                class Builder:
                    def __init__(self, path_conv, path, children, _=None):
                        self.node = Node(path_conv(path), [])
                        self.children = children
                        self.parent = None

                    def build(self, queue):
                        for builder in self.children:
                            builder.parent = self.node
                            queue.append(builder)
                        if self.parent:
                            self.parent.neighbours.append(self.node)
                            self.node.neighbours.append(self.parent)
                        return self.node

                nodes = [t.traverse(Builder)]
                i = 0
                while i < len(nodes):
                    nodes[i] = nodes[i].build(nodes)
                    i += 1
                return nodes

        Args:
            node_factory: Makes opaque objects from the keys and values of the
                trie.
            prefix: Prefix for node to start traversal, by default starts at
                root.

        Returns:
            Node object constructed by node_factory corresponding to the root
            node.
        """
        node, _ = self._get_node(prefix)
        return node.traverse(
            node_factory,
            self._key_from_path,
            list(self.__path_from_key(prefix)),
            self._items_callback,
        )

    # traverse.uses_bool_convertible_children = True


class CharTrie(Trie[V]):
    """A variant of a :class:`tarina.trie.Trie` which accepts strings as keys.

    The only difference between :class:`tarina.trie.CharTrie` and
    :class:`tarina.trie.Trie` is that when :class:`tarina.trie.CharTrie` returns keys
    back to the client (for instance when :func:`Trie.keys` method is called),
    those keys are returned as strings.

    Common example where this class can be used is a dictionary of words in
    a natural language.  For example::

        >>> import tarina.trie
        >>> t = tarina.trie.CharTrie()
        >>> t['wombat'] = True
        >>> t['woman'] = True
        >>> t['man'] = True
        >>> t['manhole'] = True
        >>> t.has_subtrie('wo')
        True
        >>> t.has_key('man')
        True
        >>> t.has_subtrie('man')
        True
        >>> t.has_subtrie('manhole')
        False
    """

    def _key_from_path(self, path: Iterable[str]):
        return "".join(path)


class StringTrie(Trie[V]):
    """:class:`tarina.trie.Trie` variant accepting strings with a separator as keys.

    The trie accepts strings as keys which are split into components using
    a separator specified during initialisation (forward slash, i.e. ``/``, by
    default).

    Common example where this class can be used is when keys are paths.  For
    example, it could map from a path to a request handler::

        import tarina.trie

        def handle_root(): pass
        def handle_admin(): pass
        def handle_admin_images(): pass

        handlers = tarina.trie.StringTrie()
        handlers[''] = handle_root
        handlers['/admin'] = handle_admin
        handlers['/admin/images'] = handle_admin_images

        request_path = '/admin/images/foo'

        handler = handlers.longest_prefix(request_path)
    """

    def __init__(
        self,
        other: MutableMapping[str, V] | Iterable[tuple[str, V]] | None = None,
        /,
        separator: str = "/",
        **kwargs: V,
    ):  # pylint: disable=differing-param-doc
        """Initialises the trie.

        Except for a ``separator`` named argument, all other arguments are
        interpreted the same way :func:`Trie.update` interprets them.

        Args:
            other: Mapping or iterable of key-value pairs to initialise the trie
                with.
            separator: A separator to use when splitting keys into paths used by
                the trie.  "/" is used if this argument is not specified.  This
                named argument is not specified on the function's prototype
                because of Python's limitations.
            **kwargs: Passed to super class initialiser.
        Raises:
            TypeError: If ``separator`` is not a string.
            ValueError: If ``separator`` is empty.
        """
        if not isinstance(separator, str):
            raise TypeError("separator must be a string")
        if not separator:
            raise ValueError("separator can not be empty")
        self._separator = separator
        super().__init__(other, **kwargs)

    @classmethod
    @overload
    def fromkeys(cls, keys: Iterable[str], value: None = None, separator="/") -> StringTrie[Any | None]: ...
    @classmethod
    @overload
    def fromkeys(cls, keys: Iterable[str], value: V1, separator="/") -> StringTrie[V1]: ...
    @classmethod
    def fromkeys(cls, keys: Iterable[str], value: Any = None, separator="/") -> StringTrie[Any]:
        trie = cls(separator=separator)
        for key in keys:
            trie[key] = value
        return trie

    @classmethod
    def _merge_impl(cls, dst, src, overwrite):
        if not isinstance(dst, StringTrie):
            raise TypeError(f"{src.__class__.__name__} cannot be merged into a {dst.__class__.__name__}")
        super()._merge_impl(dst, src, overwrite=overwrite)

    def __str__(self):
        if not self:
            return f"{self.__class__.__name__}(separator={self._separator!r})"
        return f"{self.__class__.__name__}({self._str_items()!r}, separator={self._separator!r})"

    def __repr__(self):
        return f"{self.__class__.__name__}([{self._str_items('({k!r}: {v!r})')}], separator={self._separator!r})"

    def _eq_impl(self, other):
        # If separators differ, fall back to slow generic comparison.  This is
        # because we want StringTrie(foo/bar.baz: 42, separator=/) compare equal
        # to StringTrie(foo/bar.baz: 42, separator=.) even though they have
        # different trie structure.
        if not isinstance(other, StringTrie):
            return NotImplemented
        if self._separator != other._separator:  # pylint: disable=protected-access
            return NotImplemented
        return super()._eq_impl(other)

    def _path_from_key(self, key: str):
        return key.split(self._separator)

    def _key_from_path(self, path: Iterable[str]):
        return self._separator.join(path)


if __name__ == "__main__":
    trie = CharTrie[int]()
    trie["foo"] = 1
    trie["bar"] = 2
    trie["baz"] = 3

    a = list(trie.iteritems())
    b = list(trie.prefixes("foo"))
    c = trie["ba":]

    print(a, b, list(c))  # noqa: T201

    trie1 = StringTrie[str](separator=".")
    trie1["foo.bar"] = "FooBar"
    trie1["foo.baz"] = "FooBaz"
    trie1["foo.abc.def"] = "FooAbcDef"

    print(trie1.has_subtrie("foo"))  # noqa: T201
