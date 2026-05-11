#[cfg(fast_arithmetic = "32")]
pub use super::large_powers32::*;

#[cfg(fast_arithmetic = "64")]
pub use super::large_powers64::*;
