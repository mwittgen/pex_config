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

import lsst.pex.config as pexConfig


class Unloaded(pexConfig.Config):
    i = pexConfig.Field("integer test", int, optional=True)
    f = pexConfig.Field("float test", float, default=3.0)
    b = pexConfig.Field("boolean test", bool, default=False, optional=False)
    c = pexConfig.ChoiceField("choice test", str, default="Hello",
                              allowed={"Hello": "First choice", "World": "second choice"})
    r = pexConfig.RangeField("Range test", float, default=3.0, optional=False,
                             min=3.0, inclusiveMin=True)
    ll = pexConfig.ListField("list test", int, default=[1, 2, 3], maxLength=5,
                             itemCheck=lambda x: x is not None and x > 0)
    d = pexConfig.DictField("dict test", str, str, default={"key": "value"},
                            itemCheck=lambda x: x.startswith('v'))
    n = pexConfig.Field("nan test", float, default=float("NAN"))
