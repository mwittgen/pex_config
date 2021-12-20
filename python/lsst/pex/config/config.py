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

__all__ = (
    "Config",
    "ConfigMeta",
    "Field",
    "FieldValidationError",
    "UnexpectedProxyUsageError",
    "FieldTypeVar",
)

import copy
import importlib
import io
import math
import os
import re
import shutil
import sys
import tempfile
import warnings
from typing import Any, ForwardRef, Generic, Mapping, Optional, TypeVar, Union, cast, overload

try:
    from types import GenericAlias
except ImportError:
    # cover python 3.8 usage
    GenericAlias = type(Mapping[int, int])

# if YAML is not available that's fine and we simply don't register
# the yaml representer since we know it won't be used.
try:
    import yaml
except ImportError:
    yaml = None

from .callStack import getCallStack, getStackFrame
from .comparison import compareConfigs, compareScalars, getComparisonName

if yaml:
    YamlLoaders: tuple[Any, ...] = (yaml.Loader, yaml.FullLoader, yaml.SafeLoader, yaml.UnsafeLoader)

    try:
        # CLoader is not always available
        from yaml import CLoader

        YamlLoaders += (CLoader,)
    except ImportError:
        pass
else:
    YamlLoaders = ()
    doImport = None


if int(sys.version_info.minor) < 9:
    genericAliasKwds = {"_root": True}
else:
    genericAliasKwds = {}


class _PexConfigGenericAlias(GenericAlias, **genericAliasKwds):
    """A Subclass of python's GenericAlias used in defining and instantiating
    Generics.

    This class differs from `types.GenericAlias` in that it calls a method
    named _parseTypingArgs defined on Fields. This method gives Field and its
    subclasses an opportunity to transform type parameters into class key word
    arguments. Code authors do not need to implement any returns of this object
    directly, and instead only need implement _parseTypingArgs, if a Field
    subclass differs from the base class implementation.

    This class is intended to be an implementation detail, returned from a
    Field's `__class_getitem__` method.
    """

    def __call__(self, *args: Any, **kwds: Any) -> Any:
        origin_kwargs = self._parseTypingArgs(self.__args__, kwds)
        return super().__call__(*args, **{**kwds, **origin_kwargs})


FieldTypeVar = TypeVar("FieldTypeVar")


class UnexpectedProxyUsageError(TypeError):
    """Exception raised when a proxy class is used in a context that suggests
    it should have already been converted to the thing it proxies.
    """


def _joinNamePath(prefix=None, name=None, index=None):
    """Generate nested configuration names."""
    if not prefix and not name:
        raise ValueError("Invalid name: cannot be None")
    elif not name:
        name = prefix
    elif prefix and name:
        name = prefix + "." + name

    if index is not None:
        return "%s[%r]" % (name, index)
    else:
        return name


def _autocast(x, dtype):
    """Cast a value to a type, if appropriate.

    Parameters
    ----------
    x : object
        A value.
    dtype : tpye
        Data type, such as `float`, `int`, or `str`.

    Returns
    -------
    values : object
        If appropriate, the returned value is ``x`` cast to the given type
        ``dtype``. If the cast cannot be performed the original value of
        ``x`` is returned.
    """
    if dtype == float and isinstance(x, int):
        return float(x)
    return x


def _typeStr(x):
    """Generate a fully-qualified type name.

    Returns
    -------
    `str`
        Fully-qualified type name.

    Notes
    -----
    This function is used primarily for writing config files to be executed
    later upon with the 'load' function.
    """
    if hasattr(x, "__module__") and hasattr(x, "__name__"):
        xtype = x
    else:
        xtype = type(x)
    if (sys.version_info.major <= 2 and xtype.__module__ == "__builtin__") or xtype.__module__ == "builtins":
        return xtype.__name__
    else:
        return "%s.%s" % (xtype.__module__, xtype.__name__)


if yaml:

    def _yaml_config_representer(dumper, data):
        """Represent a Config object in a form suitable for YAML.

        Stores the serialized stream as a scalar block string.
        """
        stream = io.StringIO()
        data.saveToStream(stream)
        config_py = stream.getvalue()

        # Strip multiple newlines from the end of the config
        # This simplifies the YAML to use | and not |+
        config_py = config_py.rstrip() + "\n"

        # Trailing spaces force pyyaml to use non-block form.
        # Remove the trailing spaces so it has no choice
        config_py = re.sub(r"\s+$", "\n", config_py, flags=re.MULTILINE)

        # Store the Python as a simple scalar
        return dumper.represent_scalar("lsst.pex.config.Config", config_py, style="|")

    def _yaml_config_constructor(loader, node):
        """Construct a config from YAML"""
        config_py = loader.construct_scalar(node)
        return Config._fromPython(config_py)

    # Register a generic constructor for Config and all subclasses
    # Need to register for all the loaders we would like to use
    for loader in YamlLoaders:
        yaml.add_constructor("lsst.pex.config.Config", _yaml_config_constructor, Loader=loader)


class ConfigMeta(type):
    """A metaclass for `lsst.pex.config.Config`.

    Notes
    -----
    ``ConfigMeta`` adds a dictionary containing all `~lsst.pex.config.Field`
    class attributes as a class attribute called ``_fields``, and adds
    the name of each field as an instance variable of the field itself (so you
    don't have to pass the name of the field to the field constructor).
    """

    def __init__(cls, name, bases, dict_):
        type.__init__(cls, name, bases, dict_)
        cls._fields = {}
        cls._source = getStackFrame()

        def getFields(classtype):
            fields = {}
            bases = list(classtype.__bases__)
            bases.reverse()
            for b in bases:
                fields.update(getFields(b))

            for k, v in classtype.__dict__.items():
                if isinstance(v, Field):
                    fields[k] = v
            return fields

        fields = getFields(cls)
        for k, v in fields.items():
            setattr(cls, k, copy.deepcopy(v))

    def __setattr__(cls, name, value):
        if isinstance(value, Field):
            value.name = name
            cls._fields[name] = value
        type.__setattr__(cls, name, value)


class FieldValidationError(ValueError):
    """Raised when a ``~lsst.pex.config.Field`` is not valid in a
    particular ``~lsst.pex.config.Config``.

    Parameters
    ----------
    field : `lsst.pex.config.Field`
        The field that was not valid.
    config : `lsst.pex.config.Config`
        The config containing the invalid field.
    msg : `str`
        Text describing why the field was not valid.
    """

    def __init__(self, field, config, msg):
        self.fieldType = type(field)
        """Type of the `~lsst.pex.config.Field` that incurred the error.
        """

        self.fieldName = field.name
        """Name of the `~lsst.pex.config.Field` instance that incurred the
        error (`str`).

        See also
        --------
        lsst.pex.config.Field.name
        """

        self.fullname = _joinNamePath(config._name, field.name)
        """Fully-qualified name of the `~lsst.pex.config.Field` instance
        (`str`).
        """

        self.history = config.history.setdefault(field.name, [])
        """Full history of all changes to the `~lsst.pex.config.Field`
        instance.
        """

        self.fieldSource = field.source
        """File and line number of the `~lsst.pex.config.Field` definition.
        """

        self.configSource = config._source
        error = (
            "%s '%s' failed validation: %s\n"
            "For more information see the Field definition at:\n%s"
            " and the Config definition at:\n%s"
            % (
                self.fieldType.__name__,
                self.fullname,
                msg,
                self.fieldSource.format(),
                self.configSource.format(),
            )
        )
        super().__init__(error)


class Field(Generic[FieldTypeVar]):
    """A field in a `~lsst.pex.config.Config` that supports `int`, `float`,
    `complex`, `bool`, and `str` data types.

    Parameters
    ----------
    doc : `str`
        A description of the field for users.
    dtype : type, optional
        The field's data type. ``Field`` only supports basic data types:
        `int`, `float`, `complex`, `bool`, and `str`. See
        `Field.supportedTypes`. Optional if supplied as a typing argument to
        the class.
    default : object, optional
        The field's default value.
    check : callable, optional
        A callable that is called with the field's value. This callable should
        return `False` if the value is invalid. More complex inter-field
        validation can be written as part of the
        `lsst.pex.config.Config.validate` method.
    optional : `bool`, optional
        This sets whether the field is considered optional, and therefore
        doesn't need to be set by the user. When `False`,
        `lsst.pex.config.Config.validate` fails if the field's value is `None`.
    deprecated : None or `str`, optional
        A description of why this Field is deprecated, including removal date.
        If not None, the string is appended to the docstring for this Field.

    Raises
    ------
    ValueError
        Raised when the ``dtype`` parameter is not one of the supported types
        (see `Field.supportedTypes`).

    See also
    --------
    ChoiceField
    ConfigChoiceField
    ConfigDictField
    ConfigField
    ConfigurableField
    DictField
    ListField
    RangeField
    RegistryField

    Notes
    -----
    ``Field`` instances (including those of any subclass of ``Field``) are used
    as class attributes of `~lsst.pex.config.Config` subclasses (see the
    example, below). ``Field`` attributes work like the `property` attributes
    of classes that implement custom setters and getters. `Field` attributes
    belong to the class, but operate on the instance. Formally speaking,
    `Field` attributes are `descriptors
    <https://docs.python.org/3/howto/descriptor.html>`_.

    When you access a `Field` attribute on a `Config` instance, you don't
    get the `Field` instance itself. Instead, you get the value of that field,
    which might be a simple type (`int`, `float`, `str`, `bool`) or a custom
    container type (like a `lsst.pex.config.List`) depending on the field's
    type. See the example, below.

    Fields can be annotated with a type similar to other python classes (python
    specification `here <https://peps.python.org/pep-0484/#generics>`_ ).
    See the name field in the Config example below for an example of this.
    Unlike most other uses in python, this has an effect at type checking *and*
    runtime. If the type is specified with a class annotation, it will be used
    as the value of the ``dtype`` in the ``Field`` and there is no need to
    specify it as an argument during instantiation.

    There are Some notes on dtype through type annotation syntax. Type
    annotation syntax supports supplying the argument as a string of a type
    name. i.e. "float", but this cannot be used to resolve circular references.
    Type annotation syntax can be used on an identifier in addition to Class
    assignment i.e. ``variable: Field[str] = Config.someField`` vs
    ``someField = Field[str](doc="some doc"). However, this syntax is only
    useful for annotating the type of the identifier (i.e. variable in previous
    example) and does nothing for assigning the dtype of the ``Field``.


    Examples
    --------
    Instances of ``Field`` should be used as class attributes of
    `lsst.pex.config.Config` subclasses:

    >>> from lsst.pex.config import Config, Field
    >>> class Example(Config):
    ...     myInt = Field("An integer field.", int, default=0)
    ...     name = Field[str](doc="A string Field")
    ...
    >>> print(config.myInt)
    0
    >>> config.myInt = 5
    >>> print(config.myInt)
    5
    """

    name: str
    """Identifier (variable name) used to refer to a Field within a Config
    Class.
    """

    supportedTypes = set((str, bool, float, int, complex))
    """Supported data types for field values (`set` of types).
    """

    @staticmethod
    def _parseTypingArgs(
        params: Union[tuple[type, ...], tuple[str, ...]], kwds: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        """Parses type annotations into keyword constructor arguments.

        This is a special private method that interprets type arguments (i.e.
        Field[str]) into keyword arguments to be passed on to the constructor.

        Subclasses of Field can implement this method to customize how they
        handle turning type parameters into keyword arguments (see DictField
        for an example)

        Parameters
        ----------
        params : `tuple` of `type` or `tuple` of str
            Parameters passed to the type annotation. These will either be
            types or strings. Strings are to interpreted as forward references
            and will be treated as such.
        kwds : `MutableMapping` with keys of `str` and values of `Any`
            These are the user supplied keywords that are to be passed to the
            Field constructor.

        Returns
        -------
        kwds : `MutableMapping` with keys of `str` and values of `Any`
            The mapping of keywords that will be passed onto the constructor
            of the Field. Should be filled in with any information gleaned
            from the input parameters.

        Raises
        ------
        ValueError :
            Raised if params is of incorrect length.
            Raised if a forward reference could not be resolved
            Raised if there is a conflict between params and values in kwds
        """
        if len(params) > 1:
            raise ValueError("Only single type parameters are supported")
        unpackedParams = params[0]
        if isinstance(unpackedParams, str):
            _typ = ForwardRef(unpackedParams)
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
            unpackedParams = cast(type, result)
        if "dtype" in kwds and kwds["dtype"] != unpackedParams:
            raise ValueError("Conflicting definition for dtype")
        elif "dtype" not in kwds:
            kwds = {**kwds, **{"dtype": unpackedParams}}
        return kwds

    def __class_getitem__(cls, params: Union[tuple[type, ...], type, ForwardRef]):
        return _PexConfigGenericAlias(cls, params)

    def __init__(self, doc, dtype=None, default=None, check=None, optional=False, deprecated=None):
        if dtype is None:
            raise ValueError(
                "dtype must either be supplied as an argument or as a type argument to the class"
            )
        if dtype not in self.supportedTypes:
            raise ValueError("Unsupported Field dtype %s" % _typeStr(dtype))

        source = getStackFrame()
        self._setup(
            doc=doc,
            dtype=dtype,
            default=default,
            check=check,
            optional=optional,
            source=source,
            deprecated=deprecated,
        )

    def _setup(self, doc, dtype, default, check, optional, source, deprecated):
        """Set attributes, usually during initialization."""
        self.dtype = dtype
        """Data type for the field.
        """

        # append the deprecation message to the docstring.
        if deprecated is not None:
            doc = f"{doc} Deprecated: {deprecated}"
        self.doc = doc
        """A description of the field (`str`).
        """

        self.deprecated = deprecated
        """If not None, a description of why this field is deprecated (`str`).
        """

        self.__doc__ = f"{doc} (`{dtype.__name__}`"
        if optional or default is not None:
            self.__doc__ += f", default ``{default!r}``"
        self.__doc__ += ")"

        self.default = default
        """Default value for this field.
        """

        self.check = check
        """A user-defined function that validates the value of the field.
        """

        self.optional = optional
        """Flag that determines if the field is required to be set (`bool`).

        When `False`, `lsst.pex.config.Config.validate` will fail if the
        field's value is `None`.
        """

        self.source = source
        """The stack frame where this field is defined (`list` of
        `lsst.pex.config.callStack.StackFrame`).
        """

    def rename(self, instance):
        """Rename the field in a `~lsst.pex.config.Config` (for internal use
        only).

        Parameters
        ----------
        instance : `lsst.pex.config.Config`
            The config instance that contains this field.

        Notes
        -----
        This method is invoked by the `lsst.pex.config.Config` object that
        contains this field and should not be called directly.

        Renaming is only relevant for `~lsst.pex.config.Field` instances that
        hold subconfigs. `~lsst.pex.config.Fields` that hold subconfigs should
        rename each subconfig with the full field name as generated by
        `lsst.pex.config.config._joinNamePath`.
        """
        pass

    def validate(self, instance):
        """Validate the field (for internal use only).

        Parameters
        ----------
        instance : `lsst.pex.config.Config`
            The config instance that contains this field.

        Raises
        ------
        lsst.pex.config.FieldValidationError
            Raised if verification fails.

        Notes
        -----
        This method provides basic validation:

        - Ensures that the value is not `None` if the field is not optional.
        - Ensures type correctness.
        - Ensures that the user-provided ``check`` function is valid.

        Most `~lsst.pex.config.Field` subclasses should call
        `lsst.pex.config.field.Field.validate` if they re-implement
        `~lsst.pex.config.field.Field.validate`.
        """
        value = self.__get__(instance)
        if not self.optional and value is None:
            raise FieldValidationError(self, instance, "Required value cannot be None")

    def freeze(self, instance):
        """Make this field read-only (for internal use only).

        Parameters
        ----------
        instance : `lsst.pex.config.Config`
            The config instance that contains this field.

        Notes
        -----
        Freezing is only relevant for fields that hold subconfigs. Fields which
        hold subconfigs should freeze each subconfig.

        **Subclasses should implement this method.**
        """
        pass

    def _validateValue(self, value):
        """Validate a value.

        Parameters
        ----------
        value : object
            The value being validated.

        Raises
        ------
        TypeError
            Raised if the value's type is incompatible with the field's
            ``dtype``.
        ValueError
            Raised if the value is rejected by the ``check`` method.
        """
        if value is None:
            return

        if not isinstance(value, self.dtype):
            msg = "Value %s is of incorrect type %s. Expected type %s" % (
                value,
                _typeStr(value),
                _typeStr(self.dtype),
            )
            raise TypeError(msg)
        if self.check is not None and not self.check(value):
            msg = "Value %s is not a valid value" % str(value)
            raise ValueError(msg)

    def _collectImports(self, instance, imports):
        """This function should call the _collectImports method on all config
        objects the field may own, and union them with the supplied imports
        set.

        Parameters
        ----------
        instance : instance or subclass of `lsst.pex.config.Config`
            A config object that has this field defined on it
        imports : `set`
            Set of python modules that need imported after persistence
        """
        pass

    def save(self, outfile, instance):
        """Save this field to a file (for internal use only).

        Parameters
        ----------
        outfile : file-like object
            A writeable field handle.
        instance : `Config`
            The `Config` instance that contains this field.

        Notes
        -----
        This method is invoked by the `~lsst.pex.config.Config` object that
        contains this field and should not be called directly.

        The output consists of the documentation string
        (`lsst.pex.config.Field.doc`) formatted as a Python comment. The second
        line is formatted as an assignment: ``{fullname}={value}``.

        This output can be executed with Python.
        """
        value = self.__get__(instance)
        fullname = _joinNamePath(instance._name, self.name)

        if self.deprecated and value == self.default:
            return

        # write full documentation string as comment lines
        # (i.e. first character is #)
        doc = "# " + str(self.doc).replace("\n", "\n# ")
        if isinstance(value, float) and not math.isfinite(value):
            # non-finite numbers need special care
            outfile.write("{}\n{}=float('{!r}')\n\n".format(doc, fullname, value))
        else:
            outfile.write("{}\n{}={!r}\n\n".format(doc, fullname, value))

    def toDict(self, instance):
        """Convert the field value so that it can be set as the value of an
        item in a `dict` (for internal use only).

        Parameters
        ----------
        instance : `Config`
            The `Config` that contains this field.

        Returns
        -------
        value : object
            The field's value. See *Notes*.

        Notes
        -----
        This method invoked by the owning `~lsst.pex.config.Config` object and
        should not be called directly.

        Simple values are passed through. Complex data structures must be
        manipulated. For example, a `~lsst.pex.config.Field` holding a
        subconfig should, instead of the subconfig object, return a `dict`
        where the keys are the field names in the subconfig, and the values are
        the field values in the subconfig.
        """
        return self.__get__(instance)

    @overload
    def __get__(
        self, instance: None, owner: Any = None, at: Any = None, label: str = "default"
    ) -> "Field[FieldTypeVar]":
        ...

    @overload
    def __get__(
        self, instance: "Config", owner: Any = None, at: Any = None, label: str = "default"
    ) -> FieldTypeVar:
        ...

    def __get__(self, instance, owner=None, at=None, label="default"):
        """Define how attribute access should occur on the Config instance
        This is invoked by the owning config object and should not be called
        directly

        When the field attribute is accessed on a Config class object, it
        returns the field object itself in order to allow inspection of
        Config classes.

        When the field attribute is access on a config instance, the actual
        value described by the field (and held by the Config instance) is
        returned.
        """
        if instance is None:
            return self
        else:
            # try statements are almost free in python if they succeed
            try:
                return instance._storage[self.name]
            except AttributeError:
                if not isinstance(instance, Config):
                    return self
                else:
                    raise AttributeError(
                        f"Config {instance} is missing "
                        "_storage attribute, likely"
                        " incorrectly initialized"
                    )

    def __set__(
        self, instance: "Config", value: Optional[FieldTypeVar], at: Any = None, label: str = "assignment"
    ) -> None:
        """Set an attribute on the config instance.

        Parameters
        ----------
        instance : `lsst.pex.config.Config`
            The config instance that contains this field.
        value : obj
            Value to set on this field.
        at : `list` of `lsst.pex.config.callStack.StackFrame`
            The call stack (created by
            `lsst.pex.config.callStack.getCallStack`).
        label : `str`, optional
            Event label for the history.

        Notes
        -----
        This method is invoked by the owning `lsst.pex.config.Config` object
        and should not be called directly.

        Derived `~lsst.pex.config.Field` classes may need to override the
        behavior. When overriding ``__set__``, `~lsst.pex.config.Field` authors
        should follow the following rules:

        - Do not allow modification of frozen configs.
        - Validate the new value **before** modifying the field. Except if the
          new value is `None`. `None` is special and no attempt should be made
          to validate it until `lsst.pex.config.Config.validate` is called.
        - Do not modify the `~lsst.pex.config.Config` instance to contain
          invalid values.
        - If the field is modified, update the history of the
          `lsst.pex.config.field.Field` to reflect the changes.

        In order to decrease the need to implement this method in derived
        `~lsst.pex.config.Field` types, value validation is performed in the
        `lsst.pex.config.Field._validateValue`. If only the validation step
        differs in the derived `~lsst.pex.config.Field`, it is simpler to
        implement `lsst.pex.config.Field._validateValue` than to reimplement
        ``__set__``. More complicated behavior, however, may require
        reimplementation.
        """
        if instance._frozen:
            raise FieldValidationError(self, instance, "Cannot modify a frozen Config")

        history = instance._history.setdefault(self.name, [])
        if value is not None:
            value = _autocast(value, self.dtype)
            try:
                self._validateValue(value)
            except BaseException as e:
                raise FieldValidationError(self, instance, str(e))

        instance._storage[self.name] = value
        if at is None:
            at = getCallStack()
        history.append((value, at, label))

    def __delete__(self, instance, at=None, label="deletion"):
        """Delete an attribute from a `lsst.pex.config.Config` instance.

        Parameters
        ----------
        instance : `lsst.pex.config.Config`
            The config instance that contains this field.
        at : `list` of `lsst.pex.config.callStack.StackFrame`
            The call stack (created by
            `lsst.pex.config.callStack.getCallStack`).
        label : `str`, optional
            Event label for the history.

        Notes
        -----
        This is invoked by the owning `~lsst.pex.config.Config` object and
        should not be called directly.
        """
        if at is None:
            at = getCallStack()
        self.__set__(instance, None, at=at, label=label)

    def _compare(self, instance1, instance2, shortcut, rtol, atol, output):
        """Compare a field (named `Field.name`) in two
        `~lsst.pex.config.Config` instances for equality.

        Parameters
        ----------
        instance1 : `lsst.pex.config.Config`
            Left-hand side `Config` instance to compare.
        instance2 : `lsst.pex.config.Config`
            Right-hand side `Config` instance to compare.
        shortcut : `bool`, optional
            **Unused.**
        rtol : `float`, optional
            Relative tolerance for floating point comparisons.
        atol : `float`, optional
            Absolute tolerance for floating point comparisons.
        output : callable, optional
            A callable that takes a string, used (possibly repeatedly) to
            report inequalities.

        Notes
        -----
        This method must be overridden by more complex `Field` subclasses.

        See also
        --------
        lsst.pex.config.compareScalars
        """
        v1 = getattr(instance1, self.name)
        v2 = getattr(instance2, self.name)
        name = getComparisonName(
            _joinNamePath(instance1._name, self.name), _joinNamePath(instance2._name, self.name)
        )
        return compareScalars(name, v1, v2, dtype=self.dtype, rtol=rtol, atol=atol, output=output)


class RecordingImporter:
    """Importer (for `sys.meta_path`) that records which modules are being
    imported.

    *This class does not do any importing itself.*

    Examples
    --------
    Use this class as a context manager to ensure it is properly uninstalled
    when done:

    >>> with RecordingImporter() as importer:
    ...     # import stuff
    ...     import numpy as np
    ... print("Imported: " + importer.getModules())
    """

    def __init__(self):
        self._modules = set()

    def __enter__(self):
        self.origMetaPath = sys.meta_path
        sys.meta_path = [self] + sys.meta_path  # type: ignore
        return self

    def __exit__(self, *args):
        self.uninstall()
        return False  # Don't suppress exceptions

    def uninstall(self):
        """Uninstall the importer."""
        sys.meta_path = self.origMetaPath

    def find_module(self, fullname, path=None):
        """Called as part of the ``import`` chain of events."""
        self._modules.add(fullname)
        # Return None because we don't do any importing.
        return None

    def getModules(self):
        """Get the set of modules that were imported.

        Returns
        -------
        modules : `set` of `str`
            Set of imported module names.
        """
        return self._modules


# type ignore because type checker thinks ConfigMeta is Generic when it is not
class Config(metaclass=ConfigMeta):  # type: ignore
    """Base class for configuration (*config*) objects.

    Notes
    -----
    A ``Config`` object will usually have several `~lsst.pex.config.Field`
    instances as class attributes. These are used to define most of the base
    class behavior.

    ``Config`` implements a mapping API that provides many `dict`-like methods,
    such as `keys`, `values`, `items`, `iteritems`, `iterkeys`, and
    `itervalues`. ``Config`` instances also support the ``in`` operator to
    test if a field is in the config. Unlike a `dict`, ``Config`` classes are
    not subscriptable. Instead, access individual fields as attributes of the
    configuration instance.

    Examples
    --------
    Config classes are subclasses of ``Config`` that have
    `~lsst.pex.config.Field` instances (or instances of
    `~lsst.pex.config.Field` subclasses) as class attributes:

    >>> from lsst.pex.config import Config, Field, ListField
    >>> class DemoConfig(Config):
    ...     intField = Field(doc="An integer field", dtype=int, default=42)
    ...     listField = ListField(doc="List of favorite beverages.", dtype=str,
    ...                           default=['coffee', 'green tea', 'water'])
    ...
    >>> config = DemoConfig()

    Configs support many `dict`-like APIs:

    >>> config.keys()
    ['intField', 'listField']
    >>> 'intField' in config
    True

    Individual fields can be accessed as attributes of the configuration:

    >>> config.intField
    42
    >>> config.listField.append('earl grey tea')
    >>> print(config.listField)
    ['coffee', 'green tea', 'water', 'earl grey tea']
    """

    _storage: dict[str, Any]
    _fields: dict[str, Field]
    _history: dict[str, list[Any]]
    _imports: set[Any]

    def __iter__(self):
        """Iterate over fields."""
        return self._fields.__iter__()

    def keys(self):
        """Get field names.

        Returns
        -------
        names : `dict_keys`
            List of `lsst.pex.config.Field` names.

        See also
        --------
        lsst.pex.config.Config.iterkeys
        """
        return self._storage.keys()

    def values(self):
        """Get field values.

        Returns
        -------
        values : `dict_values`
            Iterator of field values.
        """
        return self._storage.values()

    def items(self):
        """Get configurations as ``(field name, field value)`` pairs.

        Returns
        -------
        items : `dict_items`
            Iterator of tuples for each configuration. Tuple items are:

            0. Field name.
            1. Field value.
        """
        return self._storage.items()

    def __contains__(self, name):
        """!Return True if the specified field exists in this config

        @param[in] name  field name to test for
        """
        return self._storage.__contains__(name)

    def __new__(cls, *args, **kw):
        """Allocate a new `lsst.pex.config.Config` object.

        In order to ensure that all Config object are always in a proper state
        when handed to users or to derived `~lsst.pex.config.Config` classes,
        some attributes are handled at allocation time rather than at
        initialization.

        This ensures that even if a derived `~lsst.pex.config.Config` class
        implements ``__init__``, its author does not need to be concerned about
        when or even the base ``Config.__init__`` should be called.
        """
        name = kw.pop("__name", None)
        at = kw.pop("__at", getCallStack())
        # remove __label and ignore it
        kw.pop("__label", "default")

        instance = object.__new__(cls)
        instance._frozen = False
        instance._name = name
        instance._storage = {}
        instance._history = {}
        instance._imports = set()
        # load up defaults
        for field in instance._fields.values():
            instance._history[field.name] = []
            field.__set__(instance, field.default, at=at + [field.source], label="default")
        # set custom default-overides
        instance.setDefaults()
        # set constructor overides
        instance.update(__at=at, **kw)
        return instance

    def __reduce__(self):
        """Reduction for pickling (function with arguments to reproduce).

        We need to condense and reconstitute the `~lsst.pex.config.Config`,
        since it may contain lambdas (as the ``check`` elements) that cannot
        be pickled.
        """
        # The stream must be in characters to match the API but pickle
        # requires bytes
        stream = io.StringIO()
        self.saveToStream(stream)
        return (unreduceConfig, (self.__class__, stream.getvalue().encode()))

    def setDefaults(self):
        """Subclass hook for computing defaults.

        Notes
        -----
        Derived `~lsst.pex.config.Config` classes that must compute defaults
        rather than using the `~lsst.pex.config.Field` instances's defaults
        should do so here. To correctly use inherited defaults,
        implementations of ``setDefaults`` must call their base class's
        ``setDefaults``.
        """
        pass

    def update(self, **kw):
        """Update values of fields specified by the keyword arguments.

        Parameters
        ----------
        kw
            Keywords are configuration field names. Values are configuration
            field values.

        Notes
        -----
        The ``__at`` and ``__label`` keyword arguments are special internal
        keywords. They are used to strip out any internal steps from the
        history tracebacks of the config. Do not modify these keywords to
        subvert a `~lsst.pex.config.Config` instance's history.

        Examples
        --------
        This is a config with three fields:

        >>> from lsst.pex.config import Config, Field
        >>> class DemoConfig(Config):
        ...     fieldA = Field(doc='Field A', dtype=int, default=42)
        ...     fieldB = Field(doc='Field B', dtype=bool, default=True)
        ...     fieldC = Field(doc='Field C', dtype=str, default='Hello world')
        ...
        >>> config = DemoConfig()

        These are the default values of each field:

        >>> for name, value in config.iteritems():
        ...     print(f"{name}: {value}")
        ...
        fieldA: 42
        fieldB: True
        fieldC: 'Hello world'

        Using this method to update ``fieldA`` and ``fieldC``:

        >>> config.update(fieldA=13, fieldC='Updated!')

        Now the values of each field are:

        >>> for name, value in config.iteritems():
        ...     print(f"{name}: {value}")
        ...
        fieldA: 13
        fieldB: True
        fieldC: 'Updated!'
        """
        at = kw.pop("__at", getCallStack())
        label = kw.pop("__label", "update")

        for name, value in kw.items():
            try:
                field = self._fields[name]
                field.__set__(self, value, at=at, label=label)
            except KeyError:
                raise KeyError("No field of name %s exists in config type %s" % (name, _typeStr(self)))

    def load(self, filename, root="config"):
        """Modify this config in place by executing the Python code in a
        configuration file.

        Parameters
        ----------
        filename : `str`
            Name of the configuration file. A configuration file is Python
            module.
        root : `str`, optional
            Name of the variable in file that refers to the config being
            overridden.

            For example, the value of root is ``"config"`` and the file
            contains::

                config.myField = 5

            Then this config's field ``myField`` is set to ``5``.

        See also
        --------
        lsst.pex.config.Config.loadFromStream
        lsst.pex.config.Config.loadFromString
        lsst.pex.config.Config.save
        lsst.pex.config.Config.saveToStream
        lsst.pex.config.Config.saveToString
        """
        with open(filename, "r") as f:
            code = compile(f.read(), filename=filename, mode="exec")
            self.loadFromString(code, root=root, filename=filename)

    def loadFromStream(self, stream, root="config", filename=None):
        """Modify this Config in place by executing the Python code in the
        provided stream.

        Parameters
        ----------
        stream : file-like object, `str`, `bytes`, or compiled string
            Stream containing configuration override code.  If this is a
            code object, it should be compiled with ``mode="exec"``.
        root : `str`, optional
            Name of the variable in file that refers to the config being
            overridden.

            For example, the value of root is ``"config"`` and the file
            contains::

                config.myField = 5

            Then this config's field ``myField`` is set to ``5``.
        filename : `str`, optional
            Name of the configuration file, or `None` if unknown or contained
            in the stream. Used for error reporting.

        Notes
        -----
        For backwards compatibility reasons, this method accepts strings, bytes
        and code objects as well as file-like objects.  New code should use
        `loadFromString` instead for most of these types.

        See also
        --------
        lsst.pex.config.Config.load
        lsst.pex.config.Config.loadFromString
        lsst.pex.config.Config.save
        lsst.pex.config.Config.saveToStream
        lsst.pex.config.Config.saveToString
        """
        if hasattr(stream, "read"):
            if filename is None:
                filename = getattr(stream, "name", "?")
            code = compile(stream.read(), filename=filename, mode="exec")
        else:
            code = stream
        self.loadFromString(code, root=root, filename=filename)

    def loadFromString(self, code, root="config", filename=None):
        """Modify this Config in place by executing the Python code in the
        provided string.

        Parameters
        ----------
        code : `str`, `bytes`, or compiled string
            Stream containing configuration override code.
        root : `str`, optional
            Name of the variable in file that refers to the config being
            overridden.

            For example, the value of root is ``"config"`` and the file
            contains::

                config.myField = 5

            Then this config's field ``myField`` is set to ``5``.
        filename : `str`, optional
            Name of the configuration file, or `None` if unknown or contained
            in the stream. Used for error reporting.

        See also
        --------
        lsst.pex.config.Config.load
        lsst.pex.config.Config.loadFromStream
        lsst.pex.config.Config.save
        lsst.pex.config.Config.saveToStream
        lsst.pex.config.Config.saveToString
        """
        if filename is None:
            # try to determine the file name; a compiled string
            # has attribute "co_filename",
            filename = getattr(code, "co_filename", "?")
        with RecordingImporter() as importer:
            globals = {"__file__": filename}
            local = {root: self}
            exec(code, globals, local)

        self._imports.update(importer.getModules())

    def save(self, filename, root="config"):
        """Save a Python script to the named file, which, when loaded,
        reproduces this config.

        Parameters
        ----------
        filename : `str`
            Desination filename of this configuration.
        root : `str`, optional
            Name to use for the root config variable. The same value must be
            used when loading (see `lsst.pex.config.Config.load`).

        See also
        --------
        lsst.pex.config.Config.saveToStream
        lsst.pex.config.Config.saveToString
        lsst.pex.config.Config.load
        lsst.pex.config.Config.loadFromStream
        lsst.pex.config.Config.loadFromString
        """
        d = os.path.dirname(filename)
        with tempfile.NamedTemporaryFile(mode="w", delete=False, dir=d) as outfile:
            self.saveToStream(outfile, root)
            # tempfile is hardcoded to create files with mode '0600'
            # for an explantion of these antics see:
            # https://stackoverflow.com/questions/10291131/how-to-use-os-umask-in-python
            umask = os.umask(0o077)
            os.umask(umask)
            os.chmod(outfile.name, (~umask & 0o666))
            # chmod before the move so we get quasi-atomic behavior if the
            # source and dest. are on the same filesystem.
            # os.rename may not work across filesystems
            shutil.move(outfile.name, filename)

    def saveToString(self, skipImports=False):
        """Return the Python script form of this configuration as an executable
        string.

        Parameters
        ----------
        skipImports : `bool`, optional
            If `True` then do not include ``import`` statements in output,
            this is to support human-oriented output from ``pipetask`` where
            additional clutter is not useful.

        Returns
        -------
        code : `str`
            A code string readable by `loadFromString`.

        See also
        --------
        lsst.pex.config.Config.save
        lsst.pex.config.Config.saveToStream
        lsst.pex.config.Config.load
        lsst.pex.config.Config.loadFromStream
        lsst.pex.config.Config.loadFromString
        """
        buffer = io.StringIO()
        self.saveToStream(buffer, skipImports=skipImports)
        return buffer.getvalue()

    def saveToStream(self, outfile, root="config", skipImports=False):
        """Save a configuration file to a stream, which, when loaded,
        reproduces this config.

        Parameters
        ----------
        outfile : file-like object
            Destination file object write the config into. Accepts strings not
            bytes.
        root
            Name to use for the root config variable. The same value must be
            used when loading (see `lsst.pex.config.Config.load`).
        skipImports : `bool`, optional
            If `True` then do not include ``import`` statements in output,
            this is to support human-oriented output from ``pipetask`` where
            additional clutter is not useful.

        See also
        --------
        lsst.pex.config.Config.save
        lsst.pex.config.Config.saveToString
        lsst.pex.config.Config.load
        lsst.pex.config.Config.loadFromStream
        lsst.pex.config.Config.loadFromString
        """
        tmp = self._name
        self._rename(root)
        try:
            if not skipImports:
                self._collectImports()
                # Remove self from the set, as it is handled explicitly below
                self._imports.remove(self.__module__)
                configType = type(self)
                typeString = _typeStr(configType)
                outfile.write(f"import {configType.__module__}\n")
                outfile.write(
                    f"assert type({root})=={typeString}, 'config is of type %s.%s instead of "
                    f"{typeString}' % (type({root}).__module__, type({root}).__name__)\n"
                )
                for imp in sorted(self._imports):
                    if imp in sys.modules and sys.modules[imp] is not None:
                        outfile.write("import {}\n".format(imp))
            self._save(outfile)
        finally:
            self._rename(tmp)

    def freeze(self):
        """Make this config, and all subconfigs, read-only."""
        self._frozen = True
        for field in self._fields.values():
            field.freeze(self)

    def _save(self, outfile):
        """Save this config to an open stream object.

        Parameters
        ----------
        outfile : file-like object
            Destination file object write the config into. Accepts strings not
            bytes.
        """
        for field in self._fields.values():
            field.save(outfile, self)

    def _collectImports(self):
        """Adds module containing self to the list of things to import and
        then loops over all the fields in the config calling a corresponding
        collect method. The field method will call _collectImports on any
        configs it may own and return the set of things to import. This
        returned set will be merged with the set of imports for this config
        class.
        """
        self._imports.add(self.__module__)
        for name, field in self._fields.items():
            field._collectImports(self, self._imports)

    def toDict(self):
        """Make a dictionary of field names and their values.

        Returns
        -------
        dict_ : `dict`
            Dictionary with keys that are `~lsst.pex.config.Field` names.
            Values are `~lsst.pex.config.Field` values.

        See also
        --------
        lsst.pex.config.Field.toDict

        Notes
        -----
        This method uses the `~lsst.pex.config.Field.toDict` method of
        individual fields. Subclasses of `~lsst.pex.config.Field` may need to
        implement a ``toDict`` method for *this* method to work.
        """
        dict_ = {}
        for name, field in self._fields.items():
            dict_[name] = field.toDict(self)
        return dict_

    def names(self):
        """Get all the field names in the config, recursively.

        Returns
        -------
        names : `list` of `str`
            Field names.
        """
        #
        # Rather than sort out the recursion all over again use the
        # pre-existing saveToStream()
        #
        with io.StringIO() as strFd:
            self.saveToStream(strFd, "config")
            contents = strFd.getvalue()
            strFd.close()
        #
        # Pull the names out of the dumped config
        #
        keys = []
        for line in contents.split("\n"):
            if re.search(r"^((assert|import)\s+|\s*$|#)", line):
                continue

            mat = re.search(r"^(?:config\.)?([^=]+)\s*=\s*.*", line)
            if mat:
                keys.append(mat.group(1))

        return keys

    def _rename(self, name):
        """Rename this config object in its parent `~lsst.pex.config.Config`.

        Parameters
        ----------
        name : `str`
            New name for this config in its parent `~lsst.pex.config.Config`.

        Notes
        -----
        This method uses the `~lsst.pex.config.Field.rename` method of
        individual `lsst.pex.config.Field` instances.
        `lsst.pex.config.Field` subclasses may need to implement a ``rename``
        method for *this* method to work.

        See also
        --------
        lsst.pex.config.Field.rename
        """
        self._name = name
        for field in self._fields.values():
            field.rename(self)

    def validate(self):
        """Validate the Config, raising an exception if invalid.

        Raises
        ------
        lsst.pex.config.FieldValidationError
            Raised if verification fails.

        Notes
        -----
        The base class implementation performs type checks on all fields by
        calling their `~lsst.pex.config.Field.validate` methods.

        Complex single-field validation can be defined by deriving new Field
        types. For convenience, some derived `lsst.pex.config.Field`-types
        (`~lsst.pex.config.ConfigField` and
        `~lsst.pex.config.ConfigChoiceField`) are defined in `lsst.pex.config`
        that handle recursing into subconfigs.

        Inter-field relationships should only be checked in derived
        `~lsst.pex.config.Config` classes after calling this method, and base
        validation is complete.
        """
        for field in self._fields.values():
            field.validate(self)

    def formatHistory(self, name, **kwargs):
        """Format a configuration field's history to a human-readable format.

        Parameters
        ----------
        name : `str`
            Name of a `~lsst.pex.config.Field` in this config.
        kwargs
            Keyword arguments passed to `lsst.pex.config.history.format`.

        Returns
        -------
        history : `str`
            A string containing the formatted history.

        See also
        --------
        lsst.pex.config.history.format
        """
        import lsst.pex.config.history as pexHist

        return pexHist.format(self, name, **kwargs)

    history = property(lambda x: x._history)
    """Read-only history.
    """

    def __setattr__(self, attr, value, at=None, label="assignment"):
        """Set an attribute (such as a field's value).

        Notes
        -----
        Unlike normal Python objects, `~lsst.pex.config.Config` objects are
        locked such that no additional attributes nor properties may be added
        to them dynamically.

        Although this is not the standard Python behavior, it helps to protect
        users from accidentally mispelling a field name, or trying to set a
        non-existent field.
        """
        if attr in self._fields:
            if self._fields[attr].deprecated is not None:
                fullname = _joinNamePath(self._name, self._fields[attr].name)
                warnings.warn(
                    f"Config field {fullname} is deprecated: {self._fields[attr].deprecated}",
                    FutureWarning,
                    stacklevel=2,
                )
            if at is None:
                at = getCallStack()
            # This allows Field descriptors to work.
            self._fields[attr].__set__(self, value, at=at, label=label)
        elif hasattr(getattr(self.__class__, attr, None), "__set__"):
            # This allows properties and other non-Field descriptors to work.
            return object.__setattr__(self, attr, value)
        elif attr in self.__dict__ or attr in ("_name", "_history", "_storage", "_frozen", "_imports"):
            # This allows specific private attributes to work.
            self.__dict__[attr] = value
        else:
            # We throw everything else.
            raise AttributeError("%s has no attribute %s" % (_typeStr(self), attr))

    def __delattr__(self, attr, at=None, label="deletion"):
        if attr in self._fields:
            if at is None:
                at = getCallStack()
            self._fields[attr].__delete__(self, at=at, label=label)
        else:
            object.__delattr__(self, attr)

    def __eq__(self, other):
        if type(other) == type(self):
            for name in self._fields:
                thisValue = getattr(self, name)
                otherValue = getattr(other, name)
                if isinstance(thisValue, float) and math.isnan(thisValue):
                    if not math.isnan(otherValue):
                        return False
                elif thisValue != otherValue:
                    return False
            return True
        return False

    def __ne__(self, other):
        return not self.__eq__(other)

    def __str__(self):
        return str(self.toDict())

    def __repr__(self):
        return "%s(%s)" % (
            _typeStr(self),
            ", ".join("%s=%r" % (k, v) for k, v in self.toDict().items() if v is not None),
        )

    def compare(self, other, shortcut=True, rtol=1e-8, atol=1e-8, output=None):
        """Compare this configuration to another `~lsst.pex.config.Config` for
        equality.

        Parameters
        ----------
        other : `lsst.pex.config.Config`
            Other `~lsst.pex.config.Config` object to compare against this
            config.
        shortcut : `bool`, optional
            If `True`, return as soon as an inequality is found. Default is
            `True`.
        rtol : `float`, optional
            Relative tolerance for floating point comparisons.
        atol : `float`, optional
            Absolute tolerance for floating point comparisons.
        output : callable, optional
            A callable that takes a string, used (possibly repeatedly) to
            report inequalities.

        Returns
        -------
        isEqual : `bool`
            `True` when the two `lsst.pex.config.Config` instances are equal.
            `False` if there is an inequality.

        See also
        --------
        lsst.pex.config.compareConfigs

        Notes
        -----
        Unselected targets of `~lsst.pex.config.RegistryField` fields and
        unselected choices of `~lsst.pex.config.ConfigChoiceField` fields
        are not considered by this method.

        Floating point comparisons are performed by `numpy.allclose`.
        """
        name1 = self._name if self._name is not None else "config"
        name2 = other._name if other._name is not None else "config"
        name = getComparisonName(name1, name2)
        return compareConfigs(name, self, other, shortcut=shortcut, rtol=rtol, atol=atol, output=output)

    @classmethod
    def __init_subclass__(cls, **kwargs):
        """Run initialization for every subclass.

        Specifically registers the subclass with a YAML representer
        and YAML constructor (if pyyaml is available)
        """
        super().__init_subclass__(**kwargs)

        if not yaml:
            return

        yaml.add_representer(cls, _yaml_config_representer)

    @classmethod
    def _fromPython(cls, config_py):
        """Instantiate a `Config`-subclass from serialized Python form.

        Parameters
        ----------
        config_py : `str`
            A serialized form of the Config as created by
            `Config.saveToStream`.

        Returns
        -------
        config : `Config`
            Reconstructed `Config` instant.
        """
        cls = _classFromPython(config_py)
        return unreduceConfig(cls, config_py)


def _classFromPython(config_py):
    """Return the Config subclass required by this Config serialization.

    Parameters
    ----------
    config_py : `str`
        A serialized form of the Config as created by
        `Config.saveToStream`.

    Returns
    -------
    cls : `type`
        The `Config` subclass associated with this config.
    """
    # standard serialization has the form:
    #     import config.class
    #     assert type(config)==config.class.Config, ...
    # We want to parse these two lines so we can get the class itself

    # Do a single regex to avoid large string copies when splitting a
    # large config into separate lines.
    matches = re.search(r"^import ([\w.]+)\nassert .*==(.*?),", config_py)

    if not matches:
        first_line, second_line, _ = config_py.split("\n", 2)
        raise ValueError(
            "First two lines did not match expected form. Got:\n" f" - {first_line}\n" f" - {second_line}"
        )

    module_name = matches.group(1)
    module = importlib.import_module(module_name)

    # Second line
    full_name = matches.group(2)

    # Remove the module name from the full name
    if not full_name.startswith(module_name):
        raise ValueError(f"Module name ({module_name}) inconsistent with full name ({full_name})")

    # if module name is a.b.c and full name is a.b.c.d.E then
    # we need to remove a.b.c. and iterate over the remainder
    # The +1 is for the extra dot after a.b.c
    remainder = full_name[len(module_name) + 1 :]
    components = remainder.split(".")
    pytype = module
    for component in components:
        pytype = getattr(pytype, component)
    return pytype


def unreduceConfig(cls, stream):
    """Create a `~lsst.pex.config.Config` from a stream.

    Parameters
    ----------
    cls : `lsst.pex.config.Config`-type
        A `lsst.pex.config.Config` type (not an instance) that is instantiated
        with configurations in the ``stream``.
    stream : file-like object, `str`, or compiled string
        Stream containing configuration override code.

    Returns
    -------
    config : `lsst.pex.config.Config`
        Config instance.

    See also
    --------
    lsst.pex.config.Config.loadFromStream
    """
    config = cls()
    config.loadFromStream(stream)
    return config
