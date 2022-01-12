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

__all__ = ("makePropertySet",)

try:
    import lsst.daf.base as dafBase
except ImportError:
    dafBase = None


def _helper(ps, prefix, dict_):
    for k, v in dict_.items():
        name = prefix + "." + k if prefix is not None else k
        if isinstance(v, dict):
            _helper(ps, name, v)
        elif v is not None:
            ps.set(name, v)


def makePropertySet(config):
    """Convert a configuration into a `lsst.daf.base.PropertySet`.

    Parameters
    ----------
    config : `lsst.pex.config.Config`
        Configuration instance.

    Returns
    -------
    propertySet : `lsst.daf.base.PropertySet`
        A `~lsst.daf.base.PropertySet` that is equivalent to the ``config``
        instance. If ``config`` is `None` then this return value is also
        `None`.

    See also
    --------
    lsst.daf.base.PropertySet
    """
    if dafBase is None:
        raise RuntimeError("lsst.daf.base is not available")

    if config is not None:
        ps = dafBase.PropertySet()
        _helper(ps, None, config.toDict())
        return ps
    else:
        return None
