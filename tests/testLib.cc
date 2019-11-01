// This file is part of pex_config.
//
// Developed for the LSST Data Management System.
// This product includes software developed by the LSST Project
// (http://www.lsst.org).
// See the COPYRIGHT file at the top-level directory of this distribution
// for details of code ownership.
//
// This software is dual licensed under the GNU General Public License and also
// under a 3-clause BSD license. Recipients may choose which of these licenses
// to use; please see the files gpl-3.0.txt and/or bsd_license.txt,
// respectively.  If you choose the GPL option then the following text applies
// (but note that there is still no warranty even if you opt for BSD instead):
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with this program.  If not, see <http://www.gnu.org/licenses/>.

/* Various wrapped C++ classes for testing the LSST_CONTROL_FIELD macros  */

#include <sstream>
#include "pybind11/pybind11.h"
#include "pybind11/stl.h"

#include "lsst/pex/config.h"

namespace py = pybind11;

struct InnerControlObject {
    LSST_CONTROL_FIELD(p, double, "a double field");
    LSST_CONTROL_FIELD(q, std::int64_t, "a 64-bit integer field");

    explicit InnerControlObject(double p_ = 2.0) : p(p_), q(std::int64_t(1) << 33) {}
};

struct OuterControlObject {
    LSST_NESTED_CONTROL_FIELD(a, testLib, InnerControlObject, "a nested control field");
    LSST_CONTROL_FIELD(b, int, "a integer field");

    OuterControlObject(int b_ = 0) : b(b_) {
        a.q += 1;
    }
};

struct ControlObject {
    LSST_CONTROL_FIELD(foo, int, "an integer field");
    LSST_CONTROL_FIELD(bar, std::vector<std::string>, "a list of strings field");

    explicit ControlObject(int foo_=1) : foo(foo_), bar() {}
};

bool checkControl(ControlObject const & ctrl, int fooVal, std::vector<std::string> const & barVal) {
    return fooVal == ctrl.foo && barVal == ctrl.bar;
}

bool checkNestedControl(OuterControlObject const & ctrl, double apVal, std::int64_t aqVal, int bVal) {
    return ctrl.a.p == apVal && ctrl.b == bVal && ctrl.a.q == aqVal;
}

template <typename T>
struct ListView {
    explicit ListView(std::vector<T> *v_) : v{v_} {};
    std::vector<T> *v;
};

PYBIND11_MODULE(_testLib, mod) {
    py::class_<ListView<std::string>>(mod, "ListView")
        .def("append", [](ListView<std::string> &view, std::string value) {
            view.v->push_back(value);
        })
        .def("__repr__", [](ListView<std::string> &view) {
            std::ostringstream os;
            os<<"[";
            for (size_t i=0; i<view.v->size(); ++i) {
                os<<(*view.v)[i];
                if (i < view.v->size()-1) os << ", ";
            }
            os<<"]";
            return os.str();
        })
       .def("__getitem__", [](const ListView<std::string> &view, size_t i) {
            if (i >= view.v->size())
                throw py::index_error();
            return (*(view.v))[i];
        })
       .def("__setitem__", [](ListView<std::string> &view, size_t i, float v) {
            if (i >= view.v->size())
                throw py::index_error();
            (*(view.v))[i] = v;
        })
       .def("__len__", [](const ListView<std::string> &view){return view.v->size();});

    py::class_<InnerControlObject>(mod, "InnerControlObject")
        .def(py::init<>())
        .def_static("_doc_p", &InnerControlObject::_doc_p)
        .def_static("_type_p", &InnerControlObject::_type_p)
        .def_readwrite("p", &InnerControlObject::p)
        .def_static("_doc_q", &InnerControlObject::_doc_q)
        .def_static("_type_q", &InnerControlObject::_type_q)
        .def_readwrite("q", &InnerControlObject::q);

    py::class_<OuterControlObject>(mod, "OuterControlObject")
        .def(py::init<>())
        .def_static("_doc_a", &OuterControlObject::_doc_a)
        .def_static("_type_a", &OuterControlObject::_type_a)
        .def_static("_module_a", &OuterControlObject::_module_a)
        .def_readwrite("a", &OuterControlObject::a)
        .def_static("_doc_b", &OuterControlObject::_doc_b)
        .def_static("_type_b", &OuterControlObject::_type_b)
        .def_readwrite("b", &OuterControlObject::b);

    py::class_<ControlObject>(mod, "ControlObject")
        .def(py::init<>())
        .def_static("_doc_foo", &ControlObject::_doc_foo)
        .def_static("_type_foo", &ControlObject::_type_foo)
        .def_readwrite("foo", &ControlObject::foo)
        .def_static("_doc_bar", &ControlObject::_doc_bar)
        .def_static("_type_bar", &ControlObject::_type_bar)
        .def_property("bar",
                py::cpp_function([](ControlObject &c){return ListView<std::string>(&(c.bar));}, py::keep_alive<0, 1>()),
                py::cpp_function([](ControlObject &c, std::vector<std::string> &v){c.bar = v;}));

    mod.def("checkControl", &checkControl);
    mod.def("checkNestedControl", &checkNestedControl);
}
