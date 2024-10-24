#pragma once

#include <Python.h>

#ifndef LINEAR_PROBES
#define LINEAR_PROBES 9
#endif

/* This must be >= 1 */
#define PERTURB_SHIFT 5

static inline Py_ssize_t tuplesize(PyObject *ob) {
    PyVarObject *var_ob = (PyVarObject*)ob;
    return var_ob->ob_size;
}

static inline PyObject * tupleitem(PyObject *a, Py_ssize_t i)
{
    return ((PyTupleObject*)a)->ob_item[i];
}

#define FAST_COUNT 0
#define FAST_SEARCH 1
#define FAST_RSEARCH 2

Py_LOCAL_INLINE(Py_ssize_t)
ucs1lib_find_char(const Py_UCS1* s, Py_ssize_t n, Py_UCS1 ch)
{
    const Py_UCS1 *p, *e;

    p = s;
    e = s + n;
    if (n > 15) {
        p = memchr(s, ch, n);
        if (p != NULL)
            return (p - s);
        return -1;
    }
    while (p < e) {
        if (*p == ch)
            return (p - s);
        p++;
    }
    return -1;
}

#if SIZEOF_WCHAR_T == 2
#define UCS2_FAST_MEMCHR(s, c, n)              \
    (Py_UCS2 *)wmemchr((const wchar_t *)(s), c, n)
#endif

#ifdef UCS2_FAST_MEMCHR
#  define UCS2_MEMCHR_CUT_OFF 15
#else
#  define UCS2_MEMCHR_CUT_OFF 40
#endif

Py_LOCAL_INLINE(Py_ssize_t)
ucs2lib_find_char(const Py_UCS2* s, Py_ssize_t n, Py_UCS2 ch)
{
    const Py_UCS2 *p, *e;

    p = s;
    e = s + n;
    if (n > UCS2_MEMCHR_CUT_OFF) {
#ifdef UCS2_FAST_MEMCHR
        p = UCS2_FAST_MEMCHR(s, ch, n);
        if (p != NULL)
            return (p - s);
        return -1;
#else
        /* use memchr if we can choose a needle without too many likely
           false positives */
        const Py_UCS2 *s1, *e1;
        unsigned char needle = ch & 0xff;
        /* If looking for a multiple of 256, we'd have too
           many false positives looking for the '\0' byte in UCS2
           and UCS4 representations. */
        if (needle != 0) {
            do {
                void *candidate = memchr(p, needle,
                                         (e - p) * sizeof(Py_UCS2));
                if (candidate == NULL)
                    return -1;
                s1 = p;
                p = (const Py_UCS2 *)
                        _Py_ALIGN_DOWN(candidate, sizeof(Py_UCS2));
                if (*p == ch)
                    return (p - s);
                /* False positive */
                p++;
                if (p - s1 > UCS2_MEMCHR_CUT_OFF)
                    continue;
                if (e - p <= UCS2_MEMCHR_CUT_OFF)
                    break;
                e1 = p + UCS2_MEMCHR_CUT_OFF;
                while (p != e1) {
                    if (*p == ch)
                        return (p - s);
                    p++;
                }
            }
            while (e - p > UCS2_MEMCHR_CUT_OFF);
        }
#endif
    }
    while (p < e) {
        if (*p == ch)
            return (p - s);
        p++;
    }
    return -1;
}


#if SIZEOF_WCHAR_T == 4
#define UCS4_FAST_MEMCHR(s, c, n)              \
    (Py_UCS4 *)wmemchr((const wchar_t *)(s), c, n)
#endif

#ifdef UCS4_FAST_MEMCHR
#  define UCS4_MEMCHR_CUT_OFF 15
#else
#  define UCS4_MEMCHR_CUT_OFF 40
#endif

Py_LOCAL_INLINE(Py_ssize_t)
ucs4lib_find_char(const Py_UCS4* s, Py_ssize_t n, Py_UCS4 ch)
{
    const Py_UCS4 *p, *e;

    p = s;
    e = s + n;
    if (n > UCS4_MEMCHR_CUT_OFF) {
#ifdef UCS4_FAST_MEMCHR
        p = UCS4_FAST_MEMCHR(s, ch, n);
        if (p != NULL)
            return (p - s);
        return -1;
#else
        /* use memchr if we can choose a needle without too many likely
           false positives */
        const Py_UCS4 *s1, *e1;
        unsigned char needle = ch & 0xff;
        /* If looking for a multiple of 256, we'd have too
           many false positives looking for the '\0' byte in UCS2
           and UCS4 representations. */
        if (needle != 0) {
            do {
                void *candidate = memchr(p, needle,
                                         (e - p) * sizeof(Py_UCS4));
                if (candidate == NULL)
                    return -1;
                s1 = p;
                p = (const Py_UCS4 *)
                        _Py_ALIGN_DOWN(candidate, sizeof(Py_UCS4));
                if (*p == ch)
                    return (p - s);
                /* False positive */
                p++;
                if (p - s1 > UCS4_MEMCHR_CUT_OFF)
                    continue;
                if (e - p <= UCS4_MEMCHR_CUT_OFF)
                    break;
                e1 = p + UCS4_MEMCHR_CUT_OFF;
                while (p != e1) {
                    if (*p == ch)
                        return (p - s);
                    p++;
                }
            }
            while (e - p > UCS4_MEMCHR_CUT_OFF);
        }
#endif
    }
    while (p < e) {
        if (*p == ch)
            return (p - s);
        p++;
    }
    return -1;
}


static inline Py_ssize_t
findchar(const void *s, int kind, Py_ssize_t size, Py_UCS4 ch)
{
    switch (kind) {
    case PyUnicode_1BYTE_KIND:
        if ((Py_UCS1) ch != ch)
            return -1;
        return ucs1lib_find_char((const Py_UCS1 *) s, size, (Py_UCS1) ch);
    case PyUnicode_2BYTE_KIND:
        if ((Py_UCS2) ch != ch)
            return -1;
        return ucs2lib_find_char((const Py_UCS2 *) s, size, (Py_UCS2) ch);
    case PyUnicode_4BYTE_KIND:
        return ucs4lib_find_char((const Py_UCS4 *) s, size, ch);
    default:
        Py_UNREACHABLE();
    }
}

static int str_contains(PyObject *str, Py_UCS4 ch) {
    const void *buf;
    int result, kind, len;
    kind = PyUnicode_KIND(str);
    len = PyUnicode_GET_LENGTH(str);
    buf = PyUnicode_DATA(str);
    result = findchar((const char *)buf, kind, len, ch) != -1;
    return result;
}

Py_LOCAL_INLINE(int)
unicode_eq(PyObject *str1, PyObject *str2)
{
    Py_ssize_t len = PyUnicode_GET_LENGTH(str1);
    if (PyUnicode_GET_LENGTH(str2) != len) {
        return 0;
    }

    int kind = PyUnicode_KIND(str1);
    if (PyUnicode_KIND(str2) != kind) {
        return 0;
    }

    const void *data1 = PyUnicode_DATA(str1);
    const void *data2 = PyUnicode_DATA(str2);
    return (memcmp(data1, data2, len * kind) == 0);
}

#define LEFTSTRIP 0
#define RIGHTSTRIP 1
#define BOTHSTRIP 2

#if LONG_BIT >= 128
#define BLOOM_WIDTH 128
#elif LONG_BIT >= 64
#define BLOOM_WIDTH 64
#elif LONG_BIT >= 32
#define BLOOM_WIDTH 32
#else
#error "LONG_BIT is smaller than 32"
#endif

#define BLOOM_MASK unsigned long

#define BLOOM(mask, ch)     ((mask &  (1UL << ((ch) & (BLOOM_WIDTH - 1)))))

#define BLOOM_LINEBREAK(ch)                                             \
    ((ch) < 128U ? ascii_linebreak[(ch)] :                              \
     (BLOOM(bloom_linebreak, (ch)) && Py_UNICODE_ISLINEBREAK(ch)))

static inline BLOOM_MASK
make_bloom_mask(int kind, const void* ptr, Py_ssize_t len)
{
#define BLOOM_UPDATE(TYPE, MASK, PTR, LEN)             \
    do {                                               \
        TYPE *data = (TYPE *)PTR;                      \
        TYPE *end = data + LEN;                        \
        Py_UCS4 ch;                                    \
        for (; data != end; data++) {                  \
            ch = *data;                                \
            MASK |= (1UL << (ch & (BLOOM_WIDTH - 1))); \
        }                                              \
        break;                                         \
    } while (0)

    /* calculate simple bloom-style bitmask for a given unicode string */

    BLOOM_MASK mask;

    mask = 0;
    switch (kind) {
    case PyUnicode_1BYTE_KIND:
        BLOOM_UPDATE(Py_UCS1, mask, ptr, len);
        break;
    case PyUnicode_2BYTE_KIND:
        BLOOM_UPDATE(Py_UCS2, mask, ptr, len);
        break;
    case PyUnicode_4BYTE_KIND:
        BLOOM_UPDATE(Py_UCS4, mask, ptr, len);
        break;
    default:
        Py_UNREACHABLE();
    }
    return mask;

#undef BLOOM_UPDATE
}

PyObject *
str_strip(PyObject *self, int striptype, PyObject *sepobj)
{
    const void *data;
    int kind;
    Py_ssize_t i, j, len;
    BLOOM_MASK sepmask;
    Py_ssize_t seplen;

    kind = PyUnicode_KIND(self);
    data = PyUnicode_DATA(self);
    len = PyUnicode_GET_LENGTH(self);
    seplen = PyUnicode_GET_LENGTH(sepobj);
    sepmask = make_bloom_mask(PyUnicode_KIND(sepobj),
                              PyUnicode_DATA(sepobj),
                              seplen);

    i = 0;
    if (striptype != RIGHTSTRIP) {
        while (i < len) {
            Py_UCS4 ch = PyUnicode_READ(kind, data, i);
            if (!BLOOM(sepmask, ch))
                break;
            if (PyUnicode_FindChar(sepobj, ch, 0, seplen, 1) < 0)
                break;
            i++;
        }
    }

    j = len;
    if (striptype != LEFTSTRIP) {
        j--;
        while (j >= i) {
            Py_UCS4 ch = PyUnicode_READ(kind, data, j);
            if (!BLOOM(sepmask, ch))
                break;
            if (PyUnicode_FindChar(sepobj, ch, 0, seplen, 1) < 0)
                break;
            j--;
        }

        j++;
    }

    return PyUnicode_Substring(self, i, j);
}
