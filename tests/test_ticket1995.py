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

import math
import tempfile
import unittest

import lsst.pex.config as pexConf


class PexTestConfig(pexConf.Config):
    list1 = pexConf.ListField(dtype=int, default=[1, 2], doc="list1")
    f1 = pexConf.Field(dtype=float, doc="f1")
    f2 = pexConf.Field(dtype=float, doc="f2")


class EqualityTest(unittest.TestCase):
    def test(self):
        c1 = PexTestConfig()
        c2 = PexTestConfig()
        self.assertEqual(c1, c2)
        c1.list1 = [1, 2, 3, 4, 5]
        self.assertNotEqual(c1, c2)
        c2.list1 = c1.list1
        self.assertEqual(c1, c2)


class LoadSpecialTest(unittest.TestCase):
    def test(self):
        c1 = PexTestConfig()
        c2 = PexTestConfig()
        c1.list1 = None
        c1.f1 = float("nan")
        c2.f2 = float("inf")
        with tempfile.NamedTemporaryFile(mode="w") as f:
            c1.saveToStream(f.file)
            f.file.close()
            c2.load(f.name)
        self.assertEqual(c1.list1, c2.list1)
        self.assertEqual(c1.f2, c2.f2)
        self.assertTrue(math.isnan(c2.f1))


if __name__ == "__main__":
    unittest.main()
