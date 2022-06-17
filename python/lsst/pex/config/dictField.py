# This file is part of pex_config.
#
# Developed for the LSST Data Management System.
# This product includes software developed by the LSST Project
# (http://www.lsst.org).
# See the COPYRIGHT file at the top-level directory of this distribution
# for details of code ownership.
#
# This software is dual licensed under the GNU General Public License and also
# under a 3-clause BSD license. Recipients may choose which of these licenses
# to use; please see the files gpl-3.0.txt and/or bsd_license.txt,
# respectively.  If you choose the GPL option then the following text applies
# (but note that there is still no warranty even if you opt for BSD instead):
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import annotations

__all__ = ["DictField"]

import collections.abc
import sys
import weakref
from typing import Any, ForwardRef, Generic, Iterator, Mapping, Type, TypeVar, Union, cast

from .callStack import getCallStack, getStackFrame
from .comparison import compareScalars, getComparisonName
from .config import (
    Config,
    Field,
    FieldValidationError,
    UnexpectedProxyUsageError,
    _autocast,
    _joinNamePath,
    _typeStr,
)

KeyTypeVar = TypeVar("KeyTypeVar")
ItemTypeVar = TypeVar("ItemTypeVar")


if int(sys.version_info.minor) < 9:
    _bases = (collections.abc.MutableMapping, Generic[KeyTypeVar, ItemTypeVar])
else:
    _bases = (collections.abc.MutableMapping[KeyTypeVar, ItemTypeVar],)


class Dict(*_bases):
    """An internal mapping container.

    This class emulates a `dict`, but adds validation and provenance.
    """

    def __init__(self, config, field, value, at, label, setHistory=True):
        self._field = field
        self._config_ = weakref.ref(config)
        self._dict = {}
        self._history = self._config._history.setdefault(self._field.name, [])
        self.__doc__ = field.doc
        if value is not None:
            try:
                for k in value:
                    # do not set history per-item
                    self.__setitem__(k, value[k], at=at, label=label, setHistory=False)
            except TypeError:
                msg = "Value %s is of incorrect type %s. Mapping type expected." % (value, _typeStr(value))
                raise FieldValidationError(self._field, self._config, msg)
        if setHistory:
            self._history.append((dict(self._dict), at, label))

    @property
    def _config(self) -> Config:
        # Config Fields should never outlive their config class instance
        # assert that as such here
        value = self._config_()
        assert value is not None
        return value

    history = property(lambda x: x._history)
    """History (read-only).
    """

    def __getitem__(self, k: KeyTypeVar) -> ItemTypeVar:
        return self._dict[k]

    def __len__(self) -> int:
        return len(self._dict)

    def __iter__(self) -> Iterator[KeyTypeVar]:
        return iter(self._dict)

    def __contains__(self, k: Any) -> bool:
        return k in self._dict

    def __setitem__(
        self, k: KeyTypeVar, x: ItemTypeVar, at: Any = None, label: str = "setitem", setHistory: bool = True
    ) -> None:
        if self._config._frozen:
            msg = "Cannot modify a frozen Config. Attempting to set item at key %r to value %s" % (k, x)
            raise FieldValidationError(self._field, self._config, msg)

        # validate keytype
        k = _autocast(k, self._field.keytype)
        if type(k) != self._field.keytype:
            msg = "Key %r is of type %s, expected type %s" % (k, _typeStr(k), _typeStr(self._field.keytype))
            raise FieldValidationError(self._field, self._config, msg)

        # validate itemtype
        x = _autocast(x, self._field.itemtype)
        if self._field.itemtype is None:
            if type(x) not in self._field.supportedTypes and x is not None:
                msg = "Value %s at key %r is of invalid type %s" % (x, k, _typeStr(x))
                raise FieldValidationError(self._field, self._config, msg)
        else:
            if type(x) != self._field.itemtype and x is not None:
                msg = "Value %s at key %r is of incorrect type %s. Expected type %s" % (
                    x,
                    k,
                    _typeStr(x),
                    _typeStr(self._field.itemtype),
                )
                raise FieldValidationError(self._field, self._config, msg)

        # validate item using itemcheck
        if self._field.itemCheck is not None and not self._field.itemCheck(x):
            msg = "Item at key %r is not a valid value: %s" % (k, x)
            raise FieldValidationError(self._field, self._config, msg)

        if at is None:
            at = getCallStack()

        self._dict[k] = x
        if setHistory:
            self._history.append((dict(self._dict), at, label))

    def __delitem__(
        self, k: KeyTypeVar, at: Any = None, label: str = "delitem", setHistory: bool = True
    ) -> None:
        if self._config._frozen:
            raise FieldValidationError(self._field, self._config, "Cannot modify a frozen Config")

        del self._dict[k]
        if setHistory:
            if at is None:
                at = getCallStack()
            self._history.append((dict(self._dict), at, label))

    def __repr__(self):
        return repr(self._dict)

    def __str__(self):
        return str(self._dict)

    def __setattr__(self, attr, value, at=None, label="assignment"):
        if hasattr(getattr(self.__class__, attr, None), "__set__"):
            # This allows properties to work.
            object.__setattr__(self, attr, value)
        elif attr in self.__dict__ or attr in ["_field", "_config_", "_history", "_dict", "__doc__"]:
            # This allows specific private attributes to work.
            object.__setattr__(self, attr, value)
        else:
            # We throw everything else.
            msg = "%s has no attribute %s" % (_typeStr(self._field), attr)
            raise FieldValidationError(self._field, self._config, msg)

    def __reduce__(self):
        raise UnexpectedProxyUsageError(
            f"Proxy container for config field {self._field.name} cannot "
            "be pickled; it should be converted to a built-in container before "
            "being assigned to other objects or variables."
        )


class DictField(Field[Dict[KeyTypeVar, ItemTypeVar]], Generic[KeyTypeVar, ItemTypeVar]):
    """A configuration field (`~lsst.pex.config.Field` subclass) that maps keys
    and values.

    The types of both items and keys are restricted to these builtin types:
    `int`, `float`, `complex`, `bool`, and `str`). All keys share the same type
    and all values share the same type. Keys can have a different type from
    values.

    Parameters
    ----------
    doc : `str`
        A documentation string that describes the configuration field.
    keytype : {`int`, `float`, `complex`, `bool`, `str`}, optional
        The type of the mapping keys. All keys must have this type. Optional
        if keytype and itemtype are supplied as typing arguments to the class.
    itemtype : {`int`, `float`, `complex`, `bool`, `str`}, optional
        Type of the mapping values. Optional if keytype and itemtype are
        supplied as typing arguments to the class.
    default : `dict`, optional
        The default mapping.
    optional : `bool`, optional
        If `True`, the field doesn't need to have a set value.
    dictCheck : callable
        A function that validates the dictionary as a whole.
    itemCheck : callable
        A function that validates individual mapping values.
    deprecated : None or `str`, optional
        A description of why this Field is deprecated, including removal date.
        If not None, the string is appended to the docstring for this Field.

    See also
    --------
    ChoiceField
    ConfigChoiceField
    ConfigDictField
    ConfigField
    ConfigurableField
    Field
    ListField
    RangeField
    RegistryField

    Examples
    --------
    This field maps has `str` keys and `int` values:

    >>> from lsst.pex.config import Config, DictField
    >>> class MyConfig(Config):
    ...     field = DictField(
    ...         doc="Example string-to-int mapping field.",
    ...         keytype=str, itemtype=int,
    ...         default={})
    ...
    >>> config = MyConfig()
    >>> config.field['myKey'] = 42
    >>> print(config.field)
    {'myKey': 42}
    """

    DictClass: Type[Dict] = Dict

    @staticmethod
    def _parseTypingArgs(
        params: Union[tuple[type, ...], tuple[str, ...]], kwds: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        if len(params) != 2:
            raise ValueError("Only tuples of types that are length 2 are supported")
        resultParams = []
        for typ in params:
            if isinstance(typ, str):
                _typ = ForwardRef(typ)
                # type ignore below because typeshed seems to be wrong. It
                # indicates there are only 2 args, as it was in python 3.8, but
                # 3.9+ takes 3 args. Attempt in old style and new style to
                # work with both.
                try:
                    result = _typ._evaluate(globals(), locals(), set())  # type: ignore
                except TypeError:
                    # python 3.8 path
                    result = _typ._evaluate(globals(), locals())
                if result is None:
                    raise ValueError("Could not deduce type from input")
                typ = cast(type, result)
            resultParams.append(typ)
        keyType, itemType = resultParams
        results = dict(kwds)
        if (supplied := kwds.get("keytype")) and supplied != keyType:
            raise ValueError("Conflicting definition for keytype")
        else:
            results["keytype"] = keyType
        if (supplied := kwds.get("itemtype")) and supplied != itemType:
            raise ValueError("Conflicting definition for itemtype")
        else:
            results["itemtype"] = itemType
        return results

    def __init__(
        self,
        doc,
        keytype=None,
        itemtype=None,
        default=None,
        optional=False,
        dictCheck=None,
        itemCheck=None,
        deprecated=None,
    ):
        source = getStackFrame()
        self._setup(
            doc=doc,
            dtype=Dict,
            default=default,
            check=None,
            optional=optional,
            source=source,
            deprecated=deprecated,
        )
        if keytype is None:
            raise ValueError(
                "keytype must either be supplied as an argument or as a type argument to the class"
            )
        if keytype not in self.supportedTypes:
            raise ValueError("'keytype' %s is not a supported type" % _typeStr(keytype))
        elif itemtype is not None and itemtype not in self.supportedTypes:
            raise ValueError("'itemtype' %s is not a supported type" % _typeStr(itemtype))
        if dictCheck is not None and not hasattr(dictCheck, "__call__"):
            raise ValueError("'dictCheck' must be callable")
        if itemCheck is not None and not hasattr(itemCheck, "__call__"):
            raise ValueError("'itemCheck' must be callable")

        self.keytype = keytype
        self.itemtype = itemtype
        self.dictCheck = dictCheck
        self.itemCheck = itemCheck

    def validate(self, instance):
        """Validate the field's value (for internal use only).

        Parameters
        ----------
        instance : `lsst.pex.config.Config`
            The configuration that contains this field.

        Returns
        -------
        isValid : `bool`
            `True` is returned if the field passes validation criteria (see
            *Notes*). Otherwise `False`.

        Notes
        -----
        This method validates values according to the following criteria:

        - A non-optional field is not `None`.
        - If a value is not `None`, is must pass the `ConfigField.dictCheck`
          user callback functon.

        Individual item checks by the `ConfigField.itemCheck` user callback
        function are done immediately when the value is set on a key. Those
        checks are not repeated by this method.
        """
        Field.validate(self, instance)
        value = self.__get__(instance)
        if value is not None and self.dictCheck is not None and not self.dictCheck(value):
            msg = "%s is not a valid value" % str(value)
            raise FieldValidationError(self, instance, msg)

    def __set__(
        self,
        instance: Config,
        value: Union[Mapping[KeyTypeVar, ItemTypeVar], None],
        at: Any = None,
        label: str = "assignment",
    ) -> None:
        if instance._frozen:
            msg = "Cannot modify a frozen Config. Attempting to set field to value %s" % value
            raise FieldValidationError(self, instance, msg)

        if at is None:
            at = getCallStack()
        if value is not None:
            value = self.DictClass(instance, self, value, at=at, label=label)
        else:
            history = instance._history.setdefault(self.name, [])
            history.append((value, at, label))

        instance._storage[self.name] = value

    def toDict(self, instance):
        """Convert this field's key-value pairs into a regular `dict`.

        Parameters
        ----------
        instance : `lsst.pex.config.Config`
            The configuration that contains this field.

        Returns
        -------
        result : `dict` or `None`
            If this field has a value of `None`, then this method returns
            `None`. Otherwise, this method returns the field's value as a
            regular Python `dict`.
        """
        value = self.__get__(instance)
        return dict(value) if value is not None else None

    def _compare(self, instance1, instance2, shortcut, rtol, atol, output):
        """Compare two fields for equality.

        Used by `lsst.pex.ConfigDictField.compare`.

        Parameters
        ----------
        instance1 : `lsst.pex.config.Config`
            Left-hand side config instance to compare.
        instance2 : `lsst.pex.config.Config`
            Right-hand side config instance to compare.
        shortcut : `bool`
            If `True`, this function returns as soon as an inequality if found.
        rtol : `float`
            Relative tolerance for floating point comparisons.
        atol : `float`
            Absolute tolerance for floating point comparisons.
        output : callable
            A callable that takes a string, used (possibly repeatedly) to
            report inequalities.

        Returns
        -------
        isEqual : bool
            `True` if the fields are equal, `False` otherwise.

        Notes
        -----
        Floating point comparisons are performed by `numpy.allclose`.
        """
        d1 = getattr(instance1, self.name)
        d2 = getattr(instance2, self.name)
        name = getComparisonName(
            _joinNamePath(instance1._name, self.name), _joinNamePath(instance2._name, self.name)
        )
        if not compareScalars("isnone for %s" % name, d1 is None, d2 is None, output=output):
            return False
        if d1 is None and d2 is None:
            return True
        if not compareScalars("keys for %s" % name, set(d1.keys()), set(d2.keys()), output=output):
            return False
        equal = True
        for k, v1 in d1.items():
            v2 = d2[k]
            result = compareScalars(
                "%s[%r]" % (name, k), v1, v2, dtype=self.itemtype, rtol=rtol, atol=atol, output=output
            )
            if not result and shortcut:
                return False
            equal = equal and result
        return equal
