//! Keyed rate limiter used for both authenticated identities and an
//! independent public-IP abuse gate.
//!
//!   * No more than [`Limits::max_simultaneous`] requests in flight from a
//!     single IP at the same time (Python default: 10).
//!   * No more than [`Limits::max_per_day`] requests from a single IP per
//!     rolling 24-hour window (Python default: 100).
//!
//! The simultaneous count is incremented on [`Limiter::try_acquire`] and
//! decremented on the returned [`Guard`]'s `Drop` — so we never leak a slot
//! if a handler panics. The 24h budget uses a `VecDeque<Instant>` per IP and
//! cleans up old entries lazily on each acquire.
//!
//! State is held behind a single `parking_lot::Mutex`. With the production
//! limits (10 concurrent, 100/day per identity) contention is negligible.

use std::collections::{HashMap, VecDeque};
use std::sync::Arc;
use std::time::{Duration, Instant};

use parking_lot::Mutex;

/// Caps applied per caller-supplied key. The primary server key is an
/// authenticated identity; a second limiter uses the public IP.
#[derive(Clone, Copy, Debug)]
pub struct Limits {
    pub max_simultaneous: u32,
    pub max_per_day: u32,
    pub window: Duration,
}

impl Default for Limits {
    fn default() -> Self {
        Self {
            max_simultaneous: 10,
            max_per_day: 100,
            window: Duration::from_secs(60 * 60 * 24),
        }
    }
}

#[derive(Default)]
struct PerKey {
    /// Currently-in-flight count for this identity or IP.
    in_flight: u32,
    /// Wall-clock timestamps of requests within the rolling window. Older
    /// entries are pruned on each acquire so the deque does not grow without
    /// bound for chatty IPs.
    timestamps: VecDeque<Instant>,
}

pub struct Limiter {
    limits: Limits,
    state: Arc<Mutex<HashMap<String, PerKey>>>,
}

impl Limiter {
    pub fn new(limits: Limits) -> Self {
        Self {
            limits,
            state: Arc::new(Mutex::new(HashMap::new())),
        }
    }

    /// Try to reserve a slot for one request from `key`. On success returns a
    /// [`Guard`] that must be held for the duration of the request — when it
    /// drops, the in-flight count is decremented. On failure returns the
    /// reason (which the caller maps to either a [`Decision::TooManyDaily`]
    /// or [`Decision::TooManyConcurrent`] response).
    pub fn try_acquire(&self, key: impl ToString) -> Decision {
        self.try_acquire_at(key, Instant::now())
    }

    /// Same as [`try_acquire`] but lets the test suite inject the "now"
    /// timestamp deterministically — otherwise the 24h-window test would
    /// have to actually sleep for hours.
    pub fn try_acquire_at(&self, key: impl ToString, now: Instant) -> Decision {
        let key = key.to_string();
        let mut guard = self.state.lock();
        let per = guard.entry(key.clone()).or_default();

        // Prune entries that fall outside the window. Cheap because the deque
        // is in chronological order and we only ever pop the front.
        while let Some(&t) = per.timestamps.front() {
            if now.saturating_duration_since(t) >= self.limits.window {
                per.timestamps.pop_front();
            } else {
                break;
            }
        }

        if per.timestamps.len() as u32 >= self.limits.max_per_day {
            let retry_after = per
                .timestamps
                .front()
                .map(|oldest| {
                    self.limits
                        .window
                        .saturating_sub(now.saturating_duration_since(*oldest))
                })
                .unwrap_or(self.limits.window);
            return Decision::TooManyDaily { retry_after };
        }
        if per.in_flight >= self.limits.max_simultaneous {
            return Decision::TooManyConcurrent {
                retry_after: Duration::from_secs(1),
            };
        }

        per.timestamps.push_back(now);
        per.in_flight += 1;

        Decision::Allowed(Guard {
            key,
            state: self.state.clone(),
            armed: true,
        })
    }
}

/// Outcome of a [`Limiter::try_acquire`] call.
pub enum Decision {
    /// The request may proceed. The guard must live for the duration of the
    /// request — dropping it returns the slot to the pool.
    Allowed(Guard),
    /// The IP has already used its 24h budget. Maps to HTTP 429.
    TooManyDaily { retry_after: Duration },
    /// The IP is at its simultaneous-request cap. Maps to HTTP 429.
    TooManyConcurrent { retry_after: Duration },
}

pub struct Guard {
    key: String,
    state: Arc<Mutex<HashMap<String, PerKey>>>,
    /// Set to false by tests that want to forget the guard intentionally.
    /// Not exposed publicly.
    armed: bool,
}

impl Drop for Guard {
    fn drop(&mut self) {
        if !self.armed {
            return;
        }
        let mut guard = self.state.lock();
        if let Some(per) = guard.get_mut(&self.key) {
            per.in_flight = per.in_flight.saturating_sub(1);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::net::{IpAddr, Ipv4Addr};

    fn ip() -> IpAddr {
        IpAddr::V4(Ipv4Addr::new(127, 0, 0, 1))
    }

    #[test]
    fn allows_within_limits() {
        let lim = Limiter::new(Limits {
            max_simultaneous: 2,
            max_per_day: 10,
            window: Duration::from_secs(3600),
        });
        let g1 = match lim.try_acquire(ip()) {
            Decision::Allowed(g) => g,
            _ => panic!("first acquire should succeed"),
        };
        let g2 = match lim.try_acquire(ip()) {
            Decision::Allowed(g) => g,
            _ => panic!("second acquire should succeed"),
        };
        drop((g1, g2));
    }

    #[test]
    fn rejects_when_concurrent_cap_hit() {
        let lim = Limiter::new(Limits {
            max_simultaneous: 1,
            max_per_day: 10,
            window: Duration::from_secs(3600),
        });
        let _g1 = match lim.try_acquire(ip()) {
            Decision::Allowed(g) => g,
            _ => panic!("first acquire should succeed"),
        };
        assert!(matches!(
            lim.try_acquire(ip()),
            Decision::TooManyConcurrent { .. }
        ));
    }

    #[test]
    fn slot_returns_on_guard_drop() {
        let lim = Limiter::new(Limits {
            max_simultaneous: 1,
            max_per_day: 10,
            window: Duration::from_secs(3600),
        });
        let g = match lim.try_acquire(ip()) {
            Decision::Allowed(g) => g,
            _ => panic!("first acquire should succeed"),
        };
        drop(g);
        // After the guard drops we should be able to acquire again.
        assert!(matches!(lim.try_acquire(ip()), Decision::Allowed(_)));
    }

    #[test]
    fn rejects_when_daily_cap_hit() {
        let lim = Limiter::new(Limits {
            max_simultaneous: 10,
            max_per_day: 2,
            window: Duration::from_secs(3600),
        });
        let g1 = match lim.try_acquire(ip()) {
            Decision::Allowed(g) => g,
            _ => panic!(),
        };
        let g2 = match lim.try_acquire(ip()) {
            Decision::Allowed(g) => g,
            _ => panic!(),
        };
        drop((g1, g2));
        // Both timestamps still inside the window; daily budget exhausted.
        assert!(matches!(
            lim.try_acquire(ip()),
            Decision::TooManyDaily { .. }
        ));
    }

    #[test]
    fn daily_window_slides() {
        let lim = Limiter::new(Limits {
            max_simultaneous: 10,
            max_per_day: 2,
            window: Duration::from_secs(60),
        });
        let t0 = Instant::now();
        let g1 = match lim.try_acquire_at(ip(), t0) {
            Decision::Allowed(g) => g,
            _ => panic!(),
        };
        let g2 = match lim.try_acquire_at(ip(), t0 + Duration::from_secs(10)) {
            Decision::Allowed(g) => g,
            _ => panic!(),
        };
        drop((g1, g2));
        // Cap hit at t0+30s (both prior timestamps still in the 60s window).
        assert!(matches!(
            lim.try_acquire_at(ip(), t0 + Duration::from_secs(30)),
            Decision::TooManyDaily { .. }
        ));
        // At t0+120s, both prior timestamps are outside the window and pruned.
        assert!(matches!(
            lim.try_acquire_at(ip(), t0 + Duration::from_secs(120)),
            Decision::Allowed(_)
        ));
    }

    #[test]
    fn identities_are_independent_even_on_one_ip() {
        let lim = Limiter::new(Limits {
            max_simultaneous: 10,
            max_per_day: 1,
            window: Duration::from_secs(60),
        });
        drop(match lim.try_acquire("identity:alice@example.com") {
            Decision::Allowed(guard) => guard,
            _ => panic!("alice first call should pass"),
        });
        assert!(matches!(
            lim.try_acquire("identity:alice@example.com"),
            Decision::TooManyDaily { .. }
        ));
        assert!(matches!(
            lim.try_acquire("identity:bob@example.com"),
            Decision::Allowed(_)
        ));
    }

    #[test]
    fn daily_decision_reports_retry_after() {
        let lim = Limiter::new(Limits {
            max_simultaneous: 10,
            max_per_day: 1,
            window: Duration::from_secs(60),
        });
        let start = Instant::now();
        drop(match lim.try_acquire_at("user", start) {
            Decision::Allowed(guard) => guard,
            _ => panic!(),
        });
        match lim.try_acquire_at("user", start + Duration::from_secs(15)) {
            Decision::TooManyDaily { retry_after } => {
                assert_eq!(retry_after, Duration::from_secs(45));
            }
            _ => panic!("expected daily throttle"),
        }
    }
}
