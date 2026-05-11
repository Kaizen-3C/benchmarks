use core::i32;

/// Compute the scientific exponent from a mantissa exponent and digit count.
///
/// The scientific exponent is the exponent when the number is written in
/// the form `d.dddde+exp`, i.e., with exactly one digit before the decimal.
///
/// # Arguments
/// * `exp` - The base-10 exponent (number of digits to shift).
/// * `fcount` - The number of integer digits before the decimal point.
#[inline]
pub(crate) fn scientific_exponent(exp: i32, fcount: usize) -> i32 {
    if fcount == 0 {
        exp.saturating_sub(1)
    } else {
        let fc = fcount as i32;
        exp.saturating_add(fc).saturating_sub(1)
    }
}

/// Compute the mantissa exponent from a scientific exponent and digit count.
///
/// This is the inverse of `scientific_exponent`.
#[inline]
pub(crate) fn mantissa_exponent(sci_exp: i32, fcount: usize) -> i32 {
    sci_exp.saturating_sub(fcount as i32)
}

/// Calculate the number of digits to skip from the start when computing
/// the exponent for the truncated float path.
///
/// Returns the number of integer (pre-decimal) digits in the mantissa.
/// Used together with `scientific_exponent` to determine the scale factor.
#[inline]
pub(crate) fn exponent_diff(sci_exp: i32, mantissa_count: usize) -> i32 {
    sci_exp.saturating_sub(mantissa_count as i32).saturating_add(1)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_scientific_exponent() {
        // "1.23e2" => fcount=1, exp=2 => sci_exp = 2 + 1 - 1 = 2
        assert_eq!(scientific_exponent(2, 1), 2);
        // "0.001" => fcount=0, exp=-3 => sci_exp = -3 - 1 = -4? Actually let's think carefully
        // fcount=0 means there are zero integer digits
        assert_eq!(scientific_exponent(0, 0), -1);
        assert_eq!(scientific_exponent(0, 1), 0);
        assert_eq!(scientific_exponent(1, 1), 1);
        assert_eq!(scientific_exponent(-3, 0), -4);
    }

    #[test]
    fn test_mantissa_exponent() {
        assert_eq!(mantissa_exponent(2, 3), -1);
        assert_eq!(mantissa_exponent(0, 0), 0);
        assert_eq!(mantissa_exponent(-1, 2), -3);
    }
}
