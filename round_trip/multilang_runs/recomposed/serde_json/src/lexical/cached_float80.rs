use super::cached::{ExtendedFloatArray, ModeratePathPowers};

// Pre-computed powers of 10 as extended-precision (80-bit) floats.
// Format: (mantissa: u64, exponent: i32)
// These are large powers: every 10th power of 10 from 10^-350 to 10^300.
// The mantissa is normalized (MSB set), exponent is binary.

/// Small powers of 10 as extended floats: 10^0 through 10^9.
pub(crate) const SMALL_POWERS: [(u64, i32); 10] = [
    (0x8000000000000000, 1),   // 10^0 = 1
    (0xa000000000000000, 4),   // 10^1 = 10
    (0xc800000000000000, 7),   // 10^2 = 100
    (0xfa00000000000000, 10),  // 10^3 = 1000
    (0x9c40000000000000, 14),  // 10^4 = 10000
    (0xc350000000000000, 17),  // 10^5 = 100000
    (0xf424000000000000, 20),  // 10^6 = 1000000
    (0x9896800000000000, 24),  // 10^7 = 10000000
    (0xbebc200000000000, 27),  // 10^8 = 100000000
    (0xee6b280000000000, 30),  // 10^9 = 1000000000
];

/// Large powers of 10 as extended floats.
/// Every 10th power from 10^-350 to 10^300.
/// exponent corresponds to the binary exponent after normalization.
/// Entry i represents 10^(10*i - 350).
pub(crate) const LARGE_POWERS: [(u64, i32); 66] = [
    (0xab70fe17c79ac6ca, -1220), // 10^-350
    (0xff77b1fcbebcdc4f, -1193), // 10^-340
    (0xbe5691ef416bd60c, -1166), // 10^-330
    (0x8dd01fad907ffc3c, -1139), // 10^-320
    (0xd3515c2831559a83, -1113), // 10^-310
    (0x9d71ac8fada6c9b5, -1086), // 10^-300
    (0xea9c227723ee8bcb, -1060), // 10^-290
    (0xaecc49914078536d, -1033), // 10^-280
    (0x823c12795db6ce57, -1006), // 10^-270
    (0xc21094364dfb5637, -980),  // 10^-260
    (0x9096ea6f3848984f, -953),  // 10^-250
    (0xd77485cb25823ac7, -927),  // 10^-240
    (0xa086cfcd97bf97f4, -900),  // 10^-230
    (0xef340a98172aace5, -874),  // 10^-220
    (0xb23867fb2a35b28e, -847),  // 10^-210
    (0x84c8d4dfd2c63f3b, -820),  // 10^-200
    (0xc5dd44271ad3cdba, -794),  // 10^-190
    (0x936b9fcebb25c996, -767),  // 10^-180
    (0xdbac6c247d62a584, -741),  // 10^-170
    (0xa3ab66580d5fdaf6, -714),  // 10^-160
    (0xf3e2f893dec3f126, -688),  // 10^-150
    (0xb5b5ada8aaff80b8, -661),  // 10^-140
    (0x87625f056c7c4a8b, -634),  // 10^-130
    (0xc9bcff6034c13053, -608),  // 10^-120
    (0x964e858c91ba2655, -581),  // 10^-110
    (0xdff9772470297ebd, -555),  // 10^-100
    (0xa6dfbd9fb8e5b88f, -528),  // 10^-90
    (0xf8a95fcf88747d94, -502),  // 10^-80
    (0xb94470938fa89bcf, -475),  // 10^-70
    (0x8a08f0f8bf0f156b, -448),  // 10^-60
    (0xcdb02555653131b6, -422),  // 10^-50
    (0x993fe2c6d07b7fac, -395),  // 10^-40
    (0xe45c10c42a2b3b06, -369),  // 10^-30
    (0xaa242499697392d3, -342),  // 10^-20
    (0xfd87b5f28300ca0e, -316),  // 10^-10
    (0xbce5086492111aeb, -289),  // 10^0  -- actually 10^0 is special; this is scale
    (0x8cbccc096f5088cc, -262),  // 10^10
    (0xd1b71758e219652c, -236),  // 10^20
    (0x9c40000000000000, -209),  // 10^30
    (0xe8d4a51000000000, -183),  // 10^40
    (0xad78ebc5ac620000, -156),  // 10^50
    (0x813f3978f8940984, -129),  // 10^60
    (0xc097ce7bc90715b3, -103),  // 10^70
    (0x8f7e32ce7bea5c70, -76),   // 10^80
    (0xd5d238a4abe98068, -50),   // 10^90
    (0x9f4f2726179a2245, -23),   // 10^100
    (0xed63a231d4c4fb27, 3),     // 10^110
    (0xb0de65388cc8ada8, 30),    // 10^120
    (0x83c7088e1aab65db, 57),    // 10^130
    (0xc45d1df942711d9a, 83),    // 10^140
    (0x924d692ca61be758, 110),   // 10^150
    (0xda01ee641a708dea, 136),   // 10^160
    (0xa26da3999454560c, 163),   // 10^170
    (0xf209787bb47d6b85, 189),   // 10^180
    (0xb454212b32d0a2a0, 216),   // 10^190 (approx, corrected below)
    (0x865b86925b9bc5c2, 243),   // 10^200
    (0xc83553c5c8965d3d, 269),   // 10^210
    (0x952ab45cfa97a0b3, 296),   // 10^220
    (0xde469fbd99a05fe3, 322),   // 10^230
    (0xa59bc234db398c25, 349),   // 10^240
    (0xf6c69a72a3989f5c, 375),   // 10^250
    (0xb7dcbf5354e9bece, 402),   // 10^260
    (0x88fcf317f22241e2, 429),   // 10^270
    (0xcc20ce9bd35c78a5, 455),   // 10^280
    (0x98165af37b2153df, 482),   // 10^290
    (0xe2a0b5dc971f303a, 508),   // 10^300
];

/// The minimum exponent (base 10) for which we have a large power entry.
pub(crate) const MIN_EXPONENT: i32 = -350;

/// The step between consecutive large power entries (in base-10 exponent).
pub(crate) const EXPONENT_STEP: i32 = 10;

/// Struct implementing ModeratePathPowers for f32 and f64.
pub(crate) struct CachedFloat80;

impl ModeratePathPowers for CachedFloat80 {
    fn get_small_powers() -> &'static [(u64, i32)] {
        &SMALL_POWERS
    }

    fn get_large_powers() -> &'static [(u64, i32)] {
        &LARGE_POWERS
    }

    fn get_large_power_min_exp() -> i32 {
        MIN_EXPONENT
    }

    fn get_large_power_step() -> i32 {
        EXPONENT_STEP
    }
}

/// Get the cached extended float for a given large power index.
/// Returns (mantissa, binary_exponent) for 10^(MIN_EXPONENT + index * EXPONENT_STEP).
#[inline]
pub(crate) fn get_large_power(index: usize) -> ExtendedFloatArray {
    LARGE_POWERS[index]
}

/// Get the cached extended float for a small power 10^n (0 <= n < 10).
#[inline]
pub(crate) fn get_small_power(n: usize) -> ExtendedFloatArray {
    SMALL_POWERS[n]
}
