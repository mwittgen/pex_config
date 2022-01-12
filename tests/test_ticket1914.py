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

import os.path
import unittest

import lsst.pex.config as pexConf


class Config1(pexConf.Config):
    f = pexConf.Field("Config1.f", float, default=4)


class Config2(pexConf.Config):
    r = pexConf.ConfigChoiceField("Config2.r", {"c1": Config1}, default="c1")


class Config3(pexConf.Config):
    c = pexConf.ConfigField("Config3.c", Config2)


class FieldNameReportingTest(unittest.TestCase):
    def test(self):
        c3 = Config3()
        test_dir = os.path.dirname(os.path.abspath(__file__))
        c3.load(os.path.join(test_dir, "config/ticket1914.py"))


if __name__ == "__main__":
    unittest.main()
