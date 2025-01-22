import base64
import re

#
# Code modified from https://github.com/google/tink/blob/6f74b99a2bfe6677e3670799116a57268fd067fa/javascript/subtle/bytes.ts
#
# @license
# Copyright 2020 Google LLC
# SPDX-License-Identifier: Apache-2.0
#

#
# Converts the hex string to a byte array.
#
# @param hex the input
# @return the byte array output
# @throws {!Error}
# @static
#
def from_hex(hex_str: str) -> bytes:
    if len(hex_str) % 2 != 0:
        raise "Hex string length must be multiple of 2"
    arr: bytearray = bytearray()
    for i, c in enumerate(hex_str):
        if i % 2 == 0:
            arr.append(int(c, 16))
    return arr

#
# Converts a byte array to hex.
#
# @param bytes the byte array input
# @return hex the output
# @static
#
def to_hex(bytes_array: bytes) -> str:
    result: str = ""
    for i in bytes_array:
        hex_byte: str = hex(i)
        result += hex_byte if len(hex_byte) > 1 else "0" + hex_byte
    return result

#
# Turns a byte array into the string given by the concatenation of the
# characters to which the numbers correspond. Each byte is corresponding to a
# character. Does not support multi-byte characters.
#
# @param bytes Array of numbers representing
#     characters.
# @return Stringification of the array.
#
def to_byte_string(bytes_array: bytes) -> str:
    result: str = ""
    for b in bytes_array:
        result += chr(b)
    return result

#
# Base64 encode a byte array.
#
# @param bytes the byte array input
# @param opt_webSafe True indicates we should use the alternative                                                                                                          *     alphabet, which does not require escaping for use in URLs.
# @return base64 output
# @static
#
def to_base64(bytes_array: bytearray, opt_web_safe: bool = False) -> str:
    return re.sub(r'=', '', to_byte_string(base64.b64encode(bytes_array, ["-", "_"] if opt_web_safe else None)))


