# cython: language_level=3, boundscheck=False, cdivision=True, wraparound=False, initializedcheck=False, infer_types=True, binding=True


from cpython.dict cimport PyDict_Contains, PyDict_GetItem
from cpython.int cimport PyInt_AS_LONG
from cpython.list cimport PyList_Append, PyList_GET_ITEM, PyList_GET_SIZE, PyList_Insert
from cpython.unicode cimport (
    PyUnicode_GET_LENGTH,
    PyUnicode_Join,
    PyUnicode_Split,
    PyUnicode_Substring,
)


cdef extern from "Python.h":
    Py_UCS4 PyUnicode_READ_CHAR(object s, Py_ssize_t i)
    cdef Py_ssize_t PY_SSIZE_T_MAX


cdef extern from "_op.h":
    bint str_contains(object str_obj, Py_UCS4 ch)
    unicode str_strip(object str_obj, int striptype, object chars_obj)
    cdef int LEFTSTRIP
    cdef int RIGHTSTRIP
    cdef int BOTHSTRIP

cdef dict QUOTES = {'"': '"', "'": "'"}
cdef unicode CRLF = "\n\r"

cpdef inline list split(str text, str separator, bint crlf=True):
    text = str_strip(text, BOTHSTRIP, separator)
    cdef:
        bint escape = 0
        list result = []
        Py_UCS4 quotation = 0
        Py_UCS4 ch = 0
        Py_ssize_t index = 0
        Py_ssize_t length = PyUnicode_GET_LENGTH(text)
        list quoted_sep_index = []
        Py_ssize_t last_sep_index = 0
        Py_ssize_t last_quote_index = 0
        Py_ssize_t _len
        Py_ssize_t i = 0

    while index < length:
        ch = PyUnicode_READ_CHAR(text, index)
        index += 1
        if PyDict_Contains(QUOTES, ch):
            if index == 1 + escape + max(last_sep_index, last_quote_index) and quotation == 0:
                quotation = PyUnicode_READ_CHAR(<str>PyDict_GetItem(QUOTES, ch), 0)
            elif (PyList_GET_SIZE(result) == 0 or str_contains(separator, <Py_UCS4>(<object>PyList_GET_ITEM(result, PyList_GET_SIZE(result)-1))) == 0) and ch == quotation:
                quotation = 0
                last_quote_index = index
            else:
                PyList_Append(result, ch)
            if escape:
                result[PyList_GET_SIZE(result)-1] = ch
        elif str_contains(separator, ch) or (crlf and str_contains(CRLF, ch)):
            if quotation:
                PyList_Append(quoted_sep_index, PyList_GET_SIZE(result) + 1)
                PyList_Append(result, ch)
            else:
                last_sep_index = index
                if result and (<object>PyList_GET_ITEM(result, PyList_GET_SIZE(result)-1)) != '\1':
                    PyList_Append(result, '\1')
        else:
            PyList_Append(result, ch)
        escape = ch == 92
    if PyList_GET_SIZE(result) == 0:
        return []
    if quotation and PyList_GET_SIZE(quoted_sep_index):
        PyList_Insert(result, last_sep_index, PyUnicode_READ_CHAR(text,  last_quote_index or last_sep_index))
        # result[first_quoted_sep_index] = '\1'
        _len = PyList_GET_SIZE(quoted_sep_index)
        while i < _len:
            result[PyInt_AS_LONG(<object>PyList_GET_ITEM(quoted_sep_index, i))] = '\1'
            i += 1
    return PyUnicode_Split(PyUnicode_Join('', result), '\1', -1)


cpdef inline tuple split_once(str text, str separator, bint crlf=True):
    text = str_strip(text, LEFTSTRIP, separator)
    cdef:
        Py_ssize_t index = 0
        list out_text = []
        Py_UCS4 quotation = 0
        Py_UCS4 ch = 0
        bint escape = 0
        bint sep = 0
        Py_ssize_t length = PyUnicode_GET_LENGTH(text)
        Py_ssize_t first_quoted_sep_index = -1
        Py_ssize_t last_quote_index = 0
    while index < length:
        ch = PyUnicode_READ_CHAR(text, index)
        index += 1
        if str_contains(separator, ch) or (crlf and str_contains(CRLF, ch)):
            if quotation == 0:
                sep = 1
                continue
            if first_quoted_sep_index == -1:
                first_quoted_sep_index = index
        if sep == 1:
            index -= 1
            break
        if PyDict_Contains(QUOTES, ch):  # 遇到引号括起来的部分跳过分隔
            if index == 1 + escape + last_quote_index and quotation == 0:
                quotation = PyUnicode_READ_CHAR(<str>PyDict_GetItem(QUOTES, ch), 0)
            elif str_contains(separator, PyUnicode_READ_CHAR(text, index-2)) == 0 and ch == quotation:
                last_quote_index = index
                first_quoted_sep_index = -1
                quotation = 0
            else:
                PyList_Append(out_text, ch)
            if escape:
                out_text[PyList_GET_SIZE(out_text)-1] = ch
            escape = 0
        else:
            PyList_Append(out_text, ch)
        escape = ch == 92
    if index == length:
        if first_quoted_sep_index == -1:
            return PyUnicode_Join('', out_text) if last_quote_index else str_strip(text, RIGHTSTRIP, separator), ''
        return PyUnicode_Substring(text, 0, first_quoted_sep_index-1), PyUnicode_Substring(text, first_quoted_sep_index, PY_SSIZE_T_MAX)
    return PyUnicode_Join('', out_text), PyUnicode_Substring(text, index, PY_SSIZE_T_MAX)
