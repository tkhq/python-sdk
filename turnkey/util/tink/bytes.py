import base64
import re

#
# Code modified from https://github.com/google/tink/blob/6f74b99a2bfe6677e3670799116a57268fd067fa/javascript/subtle/bytes.ts
#
# @license
# Copyright 2020 Google LLC
# SPDX-License-Identifier: Apache-2.0
#

def from_hex(hex_str: str) -> bytes:
    """
    Converts the hex string to a byte array.

    Args:
        hex_str: The input string in hex format

    Returns:
        the string as an array of bytes

    Raises:
        An error if the input hex_string is of an odd length
    """

    if len(hex_str) % 2 != 0:
        raise "Hex string length must be multiple of 2"
    arr: bytearray = bytearray()
    for i, c in enumerate(hex_str):
        if i % 2 == 0:
            arr.append(int(c, 16))
    return arr


def to_hex(bytes_array: bytes) -> str:
    """
    Converts a byte array to hex.

    Args:
        bytes_array: a byte array that will be converted to hex string

    Returns:
        the input string as a byte array
    """
    result: str = ""
    for i in bytes_array:
        hex_byte: str = hex(i)
        result += hex_byte if len(hex_byte) > 1 else "0" + hex_byte
    return result


def to_byte_string(bytes_array: bytes) -> str:
    """
    Turns a byte array into the string given by the concatenation of the
    characters to which the numbers correspond. Each byte is corresponding to a
    character. Does not support multi-byte characters.

    Args:
        bytes_array: an array of bytes to convert into a string

    Returns:
         a string representation of the input byte array
    """
    result: str = ""
    for b in bytes_array:
        result += chr(b)
    return result


def to_base64(bytes_array: bytes, opt_web_safe: bool = False) -> str:
    """
    Base64 encode a byte array.

    Args:
        bytes_array: the input byte array to convert into a base64 string
        opt_web_safe: an optional parameter to indicate that should use "web-safe" encoding, default is False

    Returns:
         a base64 encoded string of the input bytes
    """
    return re.sub(r'=', '', to_byte_string(base64.b64encode(bytes_array, ["-", "_"] if opt_web_safe else None)))


