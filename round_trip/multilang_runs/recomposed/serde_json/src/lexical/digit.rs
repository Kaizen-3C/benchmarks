/// Determine if a byte is a digit character.
#[inline]
pub(crate) fn is_digit(c: u8) -> bool {
    c >= b'0' && c <= b'9'
}

/// Convert a digit character to its numeric value.
#[inline]
pub(crate) fn digit_to_u64(c: u8) -> u64 {
    (c - b'0') as u64
}

/// Convert a digit character to its numeric value as u32.
#[inline]
pub(crate) fn digit_to_u32(c: u8) -> u32 {
    (c - b'0') as u32
}
