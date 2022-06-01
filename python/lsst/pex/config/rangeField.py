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

__all__ = ["RangeField"]

from .callStack import getStackFrame
from .config import Field, _typeStr


class RangeField(Field):
    """A configuration field (`lsst.pex.config.Field` subclass) that requires
    the value to be in a specific numeric range.

    Parameters
    ----------
    doc : `str`
        A description of the field.
    dtype : {`int`-type, `float`-type}
        The field's data type: either the `int` or `float` type.
    default : `int` or `float`, optional
        Default value for the field.
    optional : `bool`, optional
        When `False`, `lsst.pex.config.Config.validate` will fail if the
        field's value is `None`.
    min : int, float, or `None`, optional
        Minimum value accepted in the range. If `None`, the range has no
        lower bound (equivalent to negative infinity).
    max : `int`, `float`, or None, optional
        Maximum value accepted in the range. If `None`, the range has no
        upper bound (equivalent to positive infinity).
    inclusiveMin : `bool`, optional
        If `True`, the ``min`` value is included in the allowed range.
    inclusiveMax : `bool`, optional
        If `True`, the ``max`` value is included in the allowed range.
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
    DictField
    Field
    ListField
    RegistryField
    """

    supportedTypes = set((int, float))
    """The set of data types allowed by `RangeField` instances (`set`
    containing `int` and `float` types).
    """

    def __init__(
        self,
        doc,
        dtype,
        default=None,
        optional=False,
        min=None,
        max=None,
        inclusiveMin=True,
        inclusiveMax=False,
        deprecated=None,
    ):
        if dtype not in self.supportedTypes:
            raise ValueError("Unsupported RangeField dtype %s" % (_typeStr(dtype)))
        source = getStackFrame()
        if min is None and max is None:
            raise ValueError("min and max cannot both be None")

        if min is not None and max is not None:
            if min > max:
                raise ValueError("min = %s > %s = max" % (min, max))
            elif min == max and not (inclusiveMin and inclusiveMax):
                raise ValueError("min = max = %s and min and max not both inclusive" % (min,))

        self.min = min
        """Minimum value accepted in the range. If `None`, the range has no
        lower bound (equivalent to negative infinity).
        """

        self.max = max
        """Maximum value accepted in the range. If `None`, the range has no
        upper bound (equivalent to positive infinity).
        """

        if inclusiveMax:
            self.maxCheck = lambda x, y: True if y is None else x <= y
        else:
            self.maxCheck = lambda x, y: True if y is None else x < y
        if inclusiveMin:
            self.minCheck = lambda x, y: True if y is None else x >= y
        else:
            self.minCheck = lambda x, y: True if y is None else x > y
        self._setup(
            doc,
            dtype=dtype,
            default=default,
            check=None,
            optional=optional,
            source=source,
            deprecated=deprecated,
        )
        self.rangeString = "%s%s,%s%s" % (
            ("[" if inclusiveMin else "("),
            ("-inf" if self.min is None else self.min),
            ("inf" if self.max is None else self.max),
            ("]" if inclusiveMax else ")"),
        )
        """String representation of the field's allowed range (`str`).
        """

        self.__doc__ += "\n\nValid Range = " + self.rangeString

    def _validateValue(self, value):
        Field._validateValue(self, value)
        if not self.minCheck(value, self.min) or not self.maxCheck(value, self.max):
            msg = "%s is outside of valid range %s" % (value, self.rangeString)
            raise ValueError(msg)
