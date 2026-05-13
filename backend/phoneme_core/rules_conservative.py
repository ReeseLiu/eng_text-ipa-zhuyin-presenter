"""Conservative phoneme token categories used by syllable analysis."""

from __future__ import annotations


VOWELS = {
    "i",
    "ɪ",
    "eɪ",
    "ɛ",
    "æ",
    "ə",
    "ʌ",
    "ɑ",
    "ɔ",
    "ʊ",
    "u",
    "aɪ",
    "aʊ",
    "oʊ",
    "ɔɪ",
    "iː",
    "uː",
    "ɑː",
    "ɔː",
    "ɜː",
    "ɐ",
    "ɚ",
    "ɝ",
    "ɔːɹ",
    "ɑːɹ",
    "ɪɹ",
}

CONSONANTS = {
    "p",
    "b",
    "t",
    "d",
    "k",
    "ɡ",
    "f",
    "v",
    "θ",
    "ð",
    "s",
    "z",
    "ʃ",
    "ʒ",
    "h",
    "tʃ",
    "dʒ",
    "m",
    "n",
    "ŋ",
    "l",
    "ɹ",
    "w",
    "j",
    "ʔ",
    "ɾ",
}


def is_vowel(token: str) -> bool:
    return token in VOWELS


def is_consonant(token: str) -> bool:
    return token in CONSONANTS
