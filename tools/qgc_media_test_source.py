#!/usr/bin/env python3
"""Tiny lab-only MJPEG/WebSocket JPEG source for QGC receiver tests.

This tool is intentionally anonymous and should only be bound to loopback or a
trusted lab network. It proves QGC network-video receiver behavior, not
PixEagle deployment, PX4, SITL, HIL, field, or aircraft behavior.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import http.server
import itertools
import socket
import sys
import time
from dataclasses import dataclass


_FALLBACK_JPEG_FRAME = base64.b64decode(
    """
/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAYEBQYFBAYGBQYHBwYIChAKCgkJChQODwwQFxQYGBcUFhYaHSUfGhsjHBYWICwgIyYnKSopGR8tMC0oMCUoKSj/2wBDAQcHBwoIChMKChMoGhYaKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCj/wAARCAAwAFADASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDyyiivTv8AhVf/AFGf/JX/AOzr5zF4/D4O3t5Wvto3t6I9ilRnVvyK9jzGivTv+FV/9Rn/AMlf/s6P+FV/9Rn/AMlf/s64/wC3sB/z8/CX+Rr9Srfy/ijzGivTv+FV/wDUZ/8AJX/7Oj/hVf8A1Gf/ACV/+zo/t7Af8/Pwl/kH1Kt/L+KPMaK9O/4VX/1Gf/JX/wCzrC8Y+Cv+Ec0yK7+3/ad8wi2eTsxlWOc7j/drWjnODrzVOnO7fk/8hTwtWC5pLT5HHUUUV6ZzBX1FZ27XVwsSkLwSWbooAySa+Xa+qdIkRLl0kYIs0TRbm6KSOCfxr5biOMZ1cPGezb/9tPRwLajNrfT9R/2W0uVdLGSbzkUtiUABwOuMdD3xTYba3it45r5pcS5MaRYzgHGST2q7YadcWBN9cJsihVtwI5zjAx6gk9RUEkL39rZvbRmYwp5ckafeGCSD9CD1rwnhmoqUqdp2do2equtbff8Ad5M6/aXdlL3e/wB+l/u+8gWxWW6VIJ1aAoZDIRyijruHqPSiWGykic2ksqyIMlZsDePbHf2q+RawXT28YELzW5jcF9wRycgE/gM+lZ76bPDFJJdKYFUcbxy59B6/Woq0ORNQgnve19Pv276+j2KjU5nrK3bz/wA/kUq4X4w/8izbf9fi/wDoD13VcL8Yf+RZtv8Ar8X/ANAes8o/32l6l4r+DI8eooor9NPngr6I/wCEg0b/AKC+nf8AgSn+NfO9FeVmeVQzDl5pNct/xt/kdOHxLoXsr3PotfEulL93WrEcY4uk6enWmr4i0dTldY08H2uk/wAa+dqK8z/Ven/z8Z0f2jL+VH0R/wAJBo3/AEF9O/8AAlP8aVvEWjtjdrGnnHTN0n+NfO1FL/Val/z8f4D/ALRl/KfRH/CQaN/0F9O/8CU/xrjPirqmn3vh63jsr61uJBdKxWKZXIGx+cA9ORXlVFb4Xh2nhq0aym3YipjpVIuLW4UUUV9EcB//2Q==
"""
)

# Small generated lab animation frames. They are embedded so this source stays
# Python-stdlib-only for testers on Windows, Linux, Raspberry Pi, or a VPS.
_LAB_FRAME_B64 = (
        # Frame 1
        """
/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAA4KCw0LCQ4NDA0QDw4RFiQXFhQUFiwgIRokNC43NjMu
MjI6QVNGOj1OPjIySGJJTlZYXV5dOEVmbWVabFNbXVn/2wBDAQ8QEBYTFioXFypZOzI7WVlZWVlZ
WVlZWVlZWVlZWVlZWVlZWVlZWVlZWVlZWVlZWVlZWVlZWVlZWVlZWVlZWVn/wAARCABIAIADASIA
AhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQA
AAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3
ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWm
p6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEA
AwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSEx
BhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElK
U1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3
uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwCpbQSX
M6wxAF26ZOPep5NOuEyQqyDBbMbBhx16elGl3CWt/HNL9xQ2eM9VIqxb6kBdRSyKsMUGXWKFcBm9
Px7+1eTFRtqdbuQRabcyKWwkahQ2ZHC8Hp19cVVkjMcjISpIOMqcj863FvbaY3rCaNGudj4nQsFI
zkdO3asRgIZ/lZZAp4I6GiSSWgJsml0+4iiEjIO2VBBZc9MjqKWTT7mMLlAxYhSqEMVJ6AgdDWmt
zaQyT30c4kklOfIYYIG4E89OKjjubK1lM4YzPJJuBXIZVPXcDxnmq5I9xXZm3NnLbBTJtKnjcjBh
n0yO9Pt9PmuYHmjaIIn3t0gBFJcxwwoFjuPOZjn5QQoHvnvS206R2l5GxO6VFC8ejA1FlfUrWw99
LuEVc+WXbGIxIC3PTjrQNLuDKkYaEl+ARKpGfTOetW9QnhnaGeK6hTYEwEQiQEAA845/OmzT2yy2
0rSRSTLKGZ4UKjaD3HHP0qnGJN2Z1zbvbTGKQoWHXawYfpUVSXTrJdTSL91nLD6E1HWb30KCiiik
MKKKKAMptRmDEbY+D6H/ABpP7Sm/ux/kf8aqszbjyevrSbm/vH869P2UOxzcz7lv+0pv7sf5H/Gj
+0pv7sf5H/GkgsL+4TfBa3Ein+JUJFRTxXFu+2eOWJvRwQf1o9lDsHO+5O2ozBiNsfB9D/jSf2lN
/dj/ACP+NVWZtx5PX1pNzf3j+dHsodg5n3Lf9pTf3Y/yP+NH9pTf3Y/yP+NVNzf3j+dG5v7x/Oj2
UOwcz7lxtRmDEbY+D6H/ABpP7Sm/ux/kf8aqszbjyevrSbm/vH86PZQ7BzPuW/7Sm/ux/kf8aP7S
m/ux/kf8aqbm/vH86Nzf3j+dHsodg5n3LjajMGI2x8H0P+NJ/aU392P8j/jVVmbceT19aTc394/n
R7KHYOZ9y3/aU392P8j/AI0f2lN/dj/I/wCNVNzf3j+dG5v7x/Oj2UOwcz7g/wB9vrWzZWn2WO3c
QC5v7oboImGUjXP32HcnBwOnc1jkZlweMmu306NT4h1NyuDFsiQHsoGP6CpxFX2NJz7Dpx55KILo
ktwm7UNQupZSckI+1R9Biq+oWV3Ywsyu+o2PWSC4O5lHqrdR9R0966KkPIwa+ehmFeM+Zu/kd7oQ
atY871OzS2kjlgZntbgF4mYc9cFT7g8VRrcvkVdIu4wPlgvyIz7EHIH5CsOvp4u6TPOas7BRRRTE
K/32+tJSv99vrSUAFFFFACv99vrSUr/fb60lABRRRQA5mbceT19a7uPV2h0az1P95scFLhEQEbs4
3E546cducVwb/fb6109ro9xaSK8OoEFQRgx5Ug9QQTgg+lZVHHl5ZdROooO7OrguYbvT1lgdXQvj
K/TvWZqurR2K+VGPOu3+VIl5OT0z/nmqh0yykTEsBVidx8hyik/7pyBSNp6woy6dssywwZNpeTHs
xPH4Yry/qVFzTlK6XSxt9ejayLMWkiSz06GZkPlzNLeAHO4ktgE/UbT9ay7DTkGo3IuYQF+0ReUD
02tJ0/KmDQ51BCajIqnsFOOufX15qK70y5gswTqErpE29UwQASeo5969RVYPRM51Vi3a5et3sJ74
oTbSSxpK+6O3IRVC8ZX+I55qikm6KW6jhtnm85YRuh2oqEH5tvbPrWbBHNbzCWC4eOQfxLwf51N5
979oNx9um84rtL5OcenWtDQsR2y2d/eXVxGohs2+WLduVpD91eeo7n2FbVlp1jeWEV3MBvnVZm/7
ZnEn55rm5/MmtorcuBHGzPgL95j1J9T0FRrHOqBVuZAoBAAJwAeo696ANKfy7rTXFrBHEY4/MeJ4
irgd2V+456HtXP7m/vH860D9pNqLY3chgHSPJ2/lmoPsf/TT9KLgV2Ztx5PX1pNzf3j+dWjaZJO/
r7Un2P8A6afpRcCtub+8fzo3N/eP51Z+x/8ATT9KrONrsvXBxQIH++31rf8A+El/6dP/ACJ/9aii
plCMtyZQUtw/4SX/AKdP/In/ANaj/hJf+nT/AMif/WooqfYw7E+yh2FPiTBI+ydP+mn/ANaobrX/
ALRbtF9m27sc+Znv9KKKFSgtbAqUU7pGd9s/6Z/rR9s/6Z/rRRWljUU3eCRs6e9J9s/6Z/rRRRYA
+2f9M/1o+2f9M/1ooosApu8EjZ096T7Z/wBM/wBaKKLAH2z/AKZ/rVZzudm6ZOaKKYj/2Q==
        """,
        # Frame 2
        """
/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAA4KCw0LCQ4NDA0QDw4RFiQXFhQUFiwgIRokNC43NjMu
MjI6QVNGOj1OPjIySGJJTlZYXV5dOEVmbWVabFNbXVn/2wBDAQ8QEBYTFioXFypZOzI7WVlZWVlZ
WVlZWVlZWVlZWVlZWVlZWVlZWVlZWVlZWVlZWVlZWVlZWVlZWVlZWVlZWVn/wAARCABIAIADASIA
AhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQA
AAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3
ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWm
p6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEA
AwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSEx
BhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElK
U1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3
uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwCpbQSX
M6wxAF26ZOPep5NOuEyQqyDBbMbBhx16elGl3CWt/HNL9xQ2eM9VIqxb6kBdRSyKsMUGXWKFcBm9
Px7+1eTFRtqdbuQRabcyKWwkahQ2ZHC8Hp19cVVkjMcjISpIOMqcj863FvbaY3rCaNGudj4nQsFI
zkdO3asRgIZ/lZZAp4I6GiSSWgJsml0+4iiEjIO2VBBZc9MjqKWTT7mMLlAxYhSqEMVJ6AgdDWmt
zaQyT30c4kklOfIYYIG4E89OKjjubK1lM4YzPJJuBXIZVPXcDxnmq5I9xXZm3NnLbBTJtKnjcjBh
n0yO9Pt9PmuYHmjaIIn3t0gBFJcxwwoFjuPOZjn5QQoHvnvS2syR2l5G2d0qqFwPRgaiyvqV0Hvp
dwirnyy7YxGJAW56cdaBpdwZUjDQkvwCJVIz6Zz1q5qE0UzQzR3UUZQJwsZEgIAB5xzj60yae2WW
2laSKSZZQzPChUbQe445+lU4xuTdmdc2720xikKFh12sGH6VFUl06yXU0i/dZyw+hNR1m99Cgooo
pDCiiigDKbUZgxG2Pg+h/wAaT+0pv7sf5H/GqrM248nr60m5v7x/OvT9lDsc3M+5b/tKb+7H+R/x
o/tKb+7H+R/xqpub+8fzo3N/eP50eyh2DmfcuNqMwYjbHwfQ/wCNJ/aU392P8j/jVVmbceT19aTc
394/nR7KHYOZ9zY0+Z51knuSsVpBjzGVSWJPRVGepx9B1rf046lcxeZAsOm25HyAIWdvcknP4/pW
ZYxCSPRbVidkrSXEgzwxBIH14X9a66vMx+I9g1CmrN9TpoQ59ZGRepqsMO4SQ6hGv3oZYuSPY5zm
ufvZj9mW9swPs5bY8bg7oX/un1B5wfzrt65u/iCarfwAkR3Vm0hXsHXkH9P1qcDiXWl7OqrvuOtT
5FzROc/tKb+7H+R/xo/tKb+7H+R/xqpub+8fzo3N/eP516vsodjl5n3LjajMGI2x8H0P+NJ/aU39
2P8AI/41VZm3Hk9fWk3N/eP50eyh2Dmfct/2lN/dj/I/40f2lN/dj/I/41U3N/eP50bm/vH86PZQ
7BzPuD/fb60lK/32+tJWpIUUUUAK/wB9vrSUr/fb60lAG7YXDNp1vNCN0+muWZB1aJup/A9frXXW
d5BfW6zW77lPUdwfQ15zb3EtrOk8EjRyocqw7VqQ6hYsxkZLmwnIwzWbfK3/AAEnj6A4rhxmDWIs
07NG1Ks6enQ7aeeK3haWZwkajJJrk7u98yO91NgUWdDa2ysMFl/ib8P5mq9xfafkNI17qDoTtW4f
bGD9ASf1FZd5dzXk3mTEZACqoGFRR0UDsKnB4FYd8zd2OrW59FsQUUUV6BgK/wB9vrSUr/fb60lA
BRRRQA5mbceT19a6A3rWfhuy8q5kilkEnyrGCH+bHJPSuef77fWuhPhxiqqb0lV6Ax8D9aiU4x3J
lNR3I5Z549FP2xFWOVALaALgj1kJ6jv9c+lYW5v7x/Ourl06/mhMMurzvERgqwJBH51T/wCEa/6e
/wDyH/8AXqfbQ7k+1h3NDTNIt7200udgoEbsbgf313Ntz+Ix+NQWGnINRuRcwgL9oi8oHptaTp+V
MGhzqCqajIqnsFOOufX15pTotyY0jOpS7Ebeo2nAPqOaPbQ7h7WHcsW72E98UJtpJY0lfdHbkIqh
eMr/ABHPNUUk3RS3UcNs83nLCN0O1FQg/Nt7Z9akg0Ka3mEsGoPHIP4lTB/nU39mXv2g3H9rTecV
2l9pzj060e2h3D2sO5Rjtls7+8uriNRDZt8sW7crSH7q89R3PsK2rLTrG8sIruYDfOqzN/2zOJPz
zVGfRpJraK3N2BHGzPgRfeY9SeeT0FRroU6oFXUZAoBAAU4APUfe70e2h3D2sO5HP5d1pri1gjiM
cfmPE8RVwO7K/cc9D2rn9zf3j+dbF9bXNtGtkb6R4MbgnIUc+maofY/+mn6Vakmro0Turorszbjy
evrSbm/vH86tG0ySd/X2pPsf/TT9Kdxlbc394/nRub+8fzqz9j/6afpVZxtdl64OKBA/32+tb/8A
wkv/AE6f+RP/AK1FFTKEZbkygpbh/wAJL/06f+RP/rUf8JL/ANOn/kT/AOtRRU+xh2J9lDsKfEmC
R9k6f9NP/rUn/CS/9On/AJE/+tRRR7GHYPZQ7B/wkv8A06f+RP8A61H/AAkv/Tp/5E/+tRRR7GHY
PZQ7CnxJgkfZOn/TT/61J/wkv/Tp/wCRP/rUUUexh2D2UOxRvdV+1zCTydmF2435/pVf7Z/0z/Wi
irUUlZGiVlZCm7wSNnT3pPtn/TP9aKKdhh9s/wCmf61Wc7nZumTmiimI/9k=
        """,
        # Frame 3
        """
/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAA4KCw0LCQ4NDA0QDw4RFiQXFhQUFiwgIRokNC43NjMu
MjI6QVNGOj1OPjIySGJJTlZYXV5dOEVmbWVabFNbXVn/2wBDAQ8QEBYTFioXFypZOzI7WVlZWVlZ
WVlZWVlZWVlZWVlZWVlZWVlZWVlZWVlZWVlZWVlZWVlZWVlZWVlZWVlZWVn/wAARCABIAIADASIA
AhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQA
AAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3
ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWm
p6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEA
AwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSEx
BhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElK
U1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3
uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwCpbQSX
M6wxAF26ZOPep5NOuEyQqyDBbMbBhx16elGl3CWt/HNL9xQ2eM9VIqxb6kBdRSyKsMUGXWKFcBm9
Px7+1eTFRtqdbuQRabcyKWwkahQ2ZHC8Hp19cVVkjMcjISpIOMqcj863FvbaY3rCaNGudj4nQsFI
zkdO3asRgIZ/lZZAp4I6GiSSWgJsml0+4iiEjIO2VBBZc9MjqKWTT7mMLlAxYhSqEMVJ6AgdDWmt
zaQyT30c4kklOfIYYIG4E89OKjjubK1lM4YzPJJuBXIZVPXcDxnmq5I9xXZm3NnLbBTJtKnjcjBh
n0yO9Pt9PmuYHmjaIIn3t0gBFJcxwwoFjuPOZjn5QQoHvnvS206R2l5GxO6VFC8ejA1FlfUrWw99
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
        """,
)

JPEG_FRAMES = tuple(
    base64.b64decode("".join(frame.split())) for frame in _LAB_FRAME_B64
) or (_FALLBACK_JPEG_FRAME,)
JPEG_FRAME = JPEG_FRAMES[0]

BOUNDARY = "pixeagle-qgc-test"
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def websocket_accept_key(client_key: str) -> str:
    digest = hashlib.sha1((client_key.strip() + WS_GUID).encode("ascii")).digest()
    return base64.b64encode(digest).decode("ascii")


def websocket_binary_frame(payload: bytes) -> bytes:
    length = len(payload)
    if length < 126:
        header = bytes([0x82, length])
    elif length <= 0xFFFF:
        header = bytes([0x82, 126]) + length.to_bytes(2, "big")
    else:
        header = bytes([0x82, 127]) + length.to_bytes(8, "big")
    return header + payload


@dataclass(frozen=True)
class ServerConfig:
    host: str
    port: int
    fps: float

    @property
    def interval(self) -> float:
        return max(0.02, 1.0 / max(self.fps, 0.1))


class QGCMediaTestHandler(http.server.BaseHTTPRequestHandler):
    server_version = "PixEagleQGCTestSource/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stderr.write(
            f"{self.log_date_time_string()} {self.client_address[0]} {fmt % args}\n"
        )

    @property
    def config(self) -> ServerConfig:
        return self.server.config  # type: ignore[attr-defined]

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler naming
        path = self.path.split("?", 1)[0]
        if path in {"/", "/health"}:
            self._send_index()
            return
        if path == "/still.jpg":
            self._send_still()
            return
        if path == "/mjpeg":
            self._send_mjpeg()
            return
        if path == "/ws":
            self._send_ws()
            return
        if path == "/ws-viewer":
            self._send_ws_viewer()
            return
        self.send_error(404, "Use /mjpeg, /ws, /ws-viewer, /still.jpg, or /health")

    def do_HEAD(self) -> None:  # noqa: N802 - stdlib handler naming
        path = self.path.split("?", 1)[0]
        if path in {"/", "/health"}:
            self._send_index(body=False)
            return
        if path == "/still.jpg":
            self._send_still(body=False)
            return
        if path == "/mjpeg":
            self._send_mjpeg_headers()
            return
        if path == "/ws-viewer":
            self._send_ws_viewer(body=False)
            return
        self.send_response(405)
        self.send_header("Allow", "GET")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _send_index(self, *, body: bool = True) -> None:
        host = self.headers.get("Host") or f"{self.config.host}:{self.config.port}"
        payload = (
            "PixEagle QGC lab media source\n"
            f"HTTP MJPEG: http://{host}/mjpeg\n"
            f"Browser WebSocket viewer: http://{host}/ws-viewer\n"
            f"WebSocket JPEG: ws://{host}/ws\n"
            f"Still JPEG: http://{host}/still.jpg\n"
            "VLC/browser address bars do not render raw ws:// JPEG frames; "
            "use /mjpeg for VLC/browser or /ws-viewer for browser WebSocket checks.\n"
            "Anonymous lab source only. Do not expose to untrusted networks.\n"
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if body:
            self.wfile.write(payload)

    def _send_still(self, *, body: bool = True) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(JPEG_FRAME)))
        self.end_headers()
        if body:
            self.wfile.write(JPEG_FRAME)

    def _send_ws_viewer(self, *, body: bool = True) -> None:
        html = b"""<!doctype html>
<meta charset="utf-8">
<title>PixEagle QGC WebSocket JPEG Viewer</title>
<style>
  body { margin: 0; background: #111820; color: #e8eef5; font: 14px system-ui, sans-serif; }
  main { min-height: 100vh; display: grid; place-items: center; gap: 12px; align-content: center; }
  img { width: min(92vw, 960px); image-rendering: auto; background: #05080c; border: 1px solid #334155; }
  code { color: #9dd7ff; }
</style>
<main>
  <img id="frame" alt="Waiting for WebSocket JPEG frames">
  <div id="status">connecting...</div>
  <code id="url"></code>
</main>
<script>
const url = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`;
document.getElementById('url').textContent = url;
const image = document.getElementById('frame');
const status = document.getElementById('status');
let count = 0;
let previousUrl = null;
const ws = new WebSocket(url);
ws.binaryType = 'blob';
ws.onopen = () => { status.textContent = 'connected, waiting for first frame...'; };
ws.onmessage = (event) => {
  if (previousUrl) URL.revokeObjectURL(previousUrl);
  previousUrl = URL.createObjectURL(new Blob([event.data], { type: 'image/jpeg' }));
  image.src = previousUrl;
  count += 1;
  status.textContent = `frames: ${count}`;
};
ws.onerror = () => { status.textContent = 'websocket error'; };
ws.onclose = () => { status.textContent += ' closed'; };
</script>
"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        if body:
            self.wfile.write(html)

    def _send_mjpeg_headers(self) -> None:
        self.send_response(200)
        self.send_header(
            "Content-Type",
            f"multipart/x-mixed-replace; boundary={BOUNDARY}",
        )
        self.send_header("Cache-Control", "no-store")
        self.send_header("Pragma", "no-cache")
        self.end_headers()

    def _send_mjpeg(self) -> None:
        self._send_mjpeg_headers()
        try:
            for frame in itertools.cycle(JPEG_FRAMES):
                self.wfile.write(f"--{BOUNDARY}\r\n".encode("ascii"))
                self.wfile.write(b"Content-Type: image/jpeg\r\n")
                self.wfile.write(f"Content-Length: {len(frame)}\r\n\r\n".encode("ascii"))
                self.wfile.write(frame)
                self.wfile.write(b"\r\n")
                self.wfile.flush()
                time.sleep(self.config.interval)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            return

    def _send_ws(self) -> None:
        key = self.headers.get("Sec-WebSocket-Key")
        upgrade = self.headers.get("Upgrade", "")
        if not key or upgrade.casefold() != "websocket":
            self.send_error(400, "WebSocket upgrade required")
            return

        self.send_response(101, "Switching Protocols")
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", websocket_accept_key(key))
        self.end_headers()

        self.connection.settimeout(5.0)
        try:
            for frame in itertools.cycle(JPEG_FRAMES):
                self.connection.sendall(websocket_binary_frame(frame))
                time.sleep(self.config.interval)
        except (BrokenPipeError, ConnectionResetError, TimeoutError, OSError):
            return


class ThreadingHTTPServer(http.server.ThreadingHTTPServer):
    config: ServerConfig


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8095)
    parser.add_argument("--fps", type=float, default=5.0)
    return parser.parse_args(argv)


def make_server(config: ServerConfig) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((config.host, config.port), QGCMediaTestHandler)
    server.config = config
    return server


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = ServerConfig(args.host, args.port, args.fps)
    server = make_server(config)
    actual_host, actual_port = server.server_address[:2]
    display_host = actual_host if actual_host not in {"0.0.0.0", "::"} else "<host-ip>"
    print("PixEagle QGC lab media source", flush=True)
    print(f"HTTP MJPEG: http://{display_host}:{actual_port}/mjpeg", flush=True)
    print(
        f"Browser WebSocket viewer: http://{display_host}:{actual_port}/ws-viewer",
        flush=True,
    )
    print(f"WebSocket JPEG: ws://{display_host}:{actual_port}/ws", flush=True)
    print("Anonymous lab source only. Stop with Ctrl-C.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
