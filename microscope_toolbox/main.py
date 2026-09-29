"""Main module."""
from typing import List
from functools import reduce
from requests import get, Response


def do_stuff(l: List[str], b: bool, s: str) -> Response:
    output = []

    for item in l:
        if b:
            output.append(f"{s}={item}")
        else:
            output.append(item)

    r = reduce("&".join, output)

    return get(f"www.terraytx.com/api/{r}")
