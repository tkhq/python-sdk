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
def fromHex(hex: str) -> bytearray:
    if len(hex) % 2 != 0:
        raise "Hex string length must be multiple of 2"
    arr: bytearray = bytearray()
    for i, c in enumerate(hex):
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
def toHex(bytes: bytearray) -> str:
    result: str = ""
    for i in bytes:
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
def toByteString(bytes: bytearray) -> str:
    result: str = ""
    for b in bytes:
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
def toBase64(bytes: bytearray, opt_webSafe: bool = True) -> str:
    encoded: str = re.sub(r'/=/g', '', base64.b64encode(toByteString(bytes)))
    return encoded if not opt_webSafe else re.sub(r'/\//g', "_", re.sub(r'/\+/g', "-", encoded))

