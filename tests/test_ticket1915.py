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

import unittest

import lsst.pex.config as pexConf


class Config1(pexConf.Config):
    f = pexConf.Field("Config1.f", float, default=4)


class Config2(pexConf.Config):
    c = pexConf.ConfigField("Config2.c", Config1)


class Config3(pexConf.Config):
    r = pexConf.ConfigChoiceField("Config3.r", {"c1": Config1, "c2": Config2}, default="c1")


class HistoryMergeTest(unittest.TestCase):
    def test(self):
        a = Config2()
        b = Config2()
        b.c.f = 3
        b.c.f = 5
        a.c = b.c

        self.assertEqual([h[0] for h in a.c.history["f"]], [4, 5])

        c = Config3()
        c.r["c1"] = b.c
        c.r["c2"] = a

        self.assertEqual([h[0] for h in c.r["c1"].history["f"]], [4, 5])
        self.assertEqual([h[0] for h in c.r["c2"].c.history["f"]], [4, 5])


if __name__ == "__main__":
    unittest.main()
