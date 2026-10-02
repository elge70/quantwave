//! Rolling rank and z-score of a single series.
//!
//! These are the normalizations used to compare a level with its own history
//! (a one-year window is the usual default). They do not know what the series
//! is. A column of chain `gextotal` values is one caller.

use crate::indicators::metadata::{IndicatorMetadata, ParamDef};
use crate::traits::Next;
use crate::utils::RingBuffer as VecDeque;

/// Fraction of the trailing window that is less than or equal to the current value.
///
/// The window includes the current bar. Output is NaN until `period` finite
/// values have been seen, and NaN if the current value or any value in the
/// window is NaN. A constant window ranks as 1.
#[derive(Debug, Clone)]
pub struct PercentRank {
    period: usize,
    buf: VecDeque<f64>,
}

impl PercentRank {
    pub fn new(period: usize) -> Self {
        let period = period.max(1);
        Self {
            period,
            buf: VecDeque::with_capacity(period),
        }
    }
}

impl Next<f64> for PercentRank {
    type Output = f64;

    fn next(&mut self, x: f64) -> Self::Output {
        self.buf.push_back(x);
        if self.buf.len() > self.period {
            self.buf.pop_front();
        }
        if self.buf.len() < self.period || self.buf.iter().any(|v| v.is_nan()) {
            return f64::NAN;
        }
        let n = self.buf.len() as f64;
        let le = self.buf.iter().filter(|v| **v <= x).count() as f64;
        le / n
    }
}

/// Rolling z-score, sample standard deviation (divide by n − 1).
///
/// NaN until `period` finite values are in the window, when `period < 2`,
/// or when the sample standard deviation is 0.
#[derive(Debug, Clone)]
pub struct Zscore {
    period: usize,
    buf: VecDeque<f64>,
}

impl Zscore {
    pub fn new(period: usize) -> Self {
        let period = period.max(2);
        Self {
            period,
            buf: VecDeque::with_capacity(period),
        }
    }
}

impl Next<f64> for Zscore {
    type Output = f64;

    fn next(&mut self, x: f64) -> Self::Output {
        self.buf.push_back(x);
        if self.buf.len() > self.period {
            self.buf.pop_front();
        }
        if self.buf.len() < self.period || self.buf.iter().any(|v| v.is_nan()) {
            return f64::NAN;
        }
        let n = self.buf.len() as f64;
        let mean = self.buf.iter().sum::<f64>() / n;
        let mut acc = 0.0;
        for v in &self.buf {
            let d = v - mean;
            acc += d * d;
        }
        let std = (acc / (n - 1.0)).sqrt();
        if std == 0.0 {
            f64::NAN
        } else {
            (x - mean) / std
        }
    }
}

pub const PERCENT_RANK_METADATA: IndicatorMetadata = IndicatorMetadata {
    name: "Percent Rank",
    description: "Where the current value sits inside its own trailing window, as the fraction of window values less than or equal to it.",
    usage: "Rank a series against its own history before comparing years. A daily chain gextotal column uses period 252. The rank is not a signal by itself; compare it with a threshold in the caller.",
    keywords: &["statistics", "rank", "percentile", "normalization"],
    ehlers_summary: "Not an Ehlers filter. Empirical percent rank of a trailing window, including the current observation.",
    params: &[ParamDef {
        name: "period",
        default: "252",
        description: "Trailing window length, in bars. 252 is one trading year of daily data.",
    }],
    formula_source: "Standard trailing percent rank. Window and 0.90 / 0.10 thresholds follow the gamma-exposure normalization in David Bergstrom, Build Alpha, Gamma Exposure (Sep 2026).",
    formula_latex: r"\mathrm{percent\_rank}_t = \frac{\#\{x_i \le x_t : i \in [t-n+1, t]\}}{n}",
    gold_standard_file: "",
    category: "Statistics",
};

pub const ZSCORE_METADATA: IndicatorMetadata = IndicatorMetadata {
    name: "Rolling Z-Score",
    description: "How many sample standard deviations the current value is from its trailing mean.",
    usage: "Normalize a drifting series. A daily chain gextotal column uses period 252. Zero variance returns NaN.",
    keywords: &["statistics", "zscore", "normalization"],
    ehlers_summary: "Not an Ehlers filter. Rolling z-score with the sample standard deviation (n − 1).",
    params: &[ParamDef {
        name: "period",
        default: "252",
        description: "Trailing window length, in bars. Must be at least 2.",
    }],
    formula_source: "Standard rolling z-score. The 252-bar window and ±2 thresholds follow David Bergstrom, Build Alpha, Gamma Exposure (Sep 2026).",
    formula_latex: r"z_t = (x_t - \mu_n) / s_n,\quad s_n^2 = \sum (x_i - \mu_n)^2 / (n - 1)",
    gold_standard_file: "",
    category: "Statistics",
};

#[cfg(test)]
mod tests {
    use super::*;
    use approx::assert_relative_eq;
    use proptest::prelude::*;

    fn replay<I: Next<f64, Output = f64>>(mut ind: I, xs: &[f64]) -> Vec<f64> {
        xs.iter().copied().map(|x| ind.next(x)).collect()
    }

    #[test]
    fn percent_rank_known_window() {
        let out = replay(PercentRank::new(5), &[1.0, 2.0, 3.0, 4.0, 5.0]);
        assert!(out[..4].iter().all(|v| v.is_nan()));
        assert_relative_eq!(out[4], 1.0);
        let out = replay(PercentRank::new(5), &[1.0, 2.0, 3.0, 4.0, 3.0]);
        // window 1,2,3,4,3 — values <= 3: 1,2,3,3 → 4/5
        assert_relative_eq!(out[4], 0.8);
    }

    #[test]
    fn percent_rank_constant_is_one() {
        let out = replay(PercentRank::new(3), &[2.0, 2.0, 2.0]);
        assert_relative_eq!(out[2], 1.0);
    }

    #[test]
    fn zscore_known_window() {
        let out = replay(Zscore::new(3), &[1.0, 2.0, 3.0]);
        assert!(out[0].is_nan() && out[1].is_nan());
        // mean 2, sample std 1, z of 3 is 1
        assert_relative_eq!(out[2], 1.0);
    }

    #[test]
    fn zscore_zero_variance_is_nan() {
        let out = replay(Zscore::new(3), &[4.0, 4.0, 4.0]);
        assert!(out[2].is_nan());
    }

    #[test]
    fn nan_in_window_poisons_output() {
        let out = replay(PercentRank::new(3), &[1.0, f64::NAN, 3.0, 4.0, 5.0]);
        assert!(out[2].is_nan());
        assert!(out[3].is_nan());
        assert!(out[4].is_finite());
    }

    proptest! {
        #[test]
        fn test_percent_rank_parity(xs in prop::collection::vec(-1000.0..1000.0f64, 1..40), period in 2usize..12) {
            let once = replay(PercentRank::new(period), &xs);
            let twice = replay(PercentRank::new(period), &xs);
            prop_assert_eq!(once.len(), twice.len());
            for (a, b) in once.iter().zip(twice.iter()) {
                prop_assert_eq!(a.is_nan(), b.is_nan());
                if a.is_finite() {
                    prop_assert!((a - b).abs() < 1e-12);
                }
            }
        }

        #[test]
        fn test_zscore_parity(xs in prop::collection::vec(-1000.0..1000.0f64, 2..40), period in 2usize..12) {
            let once = replay(Zscore::new(period), &xs);
            let twice = replay(Zscore::new(period), &xs);
            for (a, b) in once.iter().zip(twice.iter()) {
                prop_assert_eq!(a.is_nan(), b.is_nan());
                if a.is_finite() && b.is_finite() {
                    prop_assert!((a - b).abs() < 1e-9);
                }
            }
        }
    }

    #[test]
    fn streaming_matches_replay() {
        let xs = [1.0, 3.0, 2.0, 8.0, 5.0, 5.0, 0.5, 4.0];
        let once = replay(PercentRank::new(4), &xs);
        let twice = replay(PercentRank::new(4), &xs);
        for (a, b) in once.iter().zip(twice.iter()) {
            assert_eq!(a.is_nan(), b.is_nan());
            if a.is_finite() {
                assert_relative_eq!(a, b);
            }
        }
        let once = replay(Zscore::new(4), &xs);
        let twice = replay(Zscore::new(4), &xs);
        for (a, b) in once.iter().zip(twice.iter()) {
            assert_eq!(a.is_nan(), b.is_nan());
            if a.is_finite() {
                assert_relative_eq!(a, b);
            }
        }
    }
}
