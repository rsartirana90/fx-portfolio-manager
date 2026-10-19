"""Causal price models. Pure Python; no market connections or order functions.

All conditional moments are log-return moments over horizon_bars. Conditional
uncertainty excludes parameter-estimation uncertainty. No profitability claim.
"""
from dataclasses import asdict, dataclass
import math
from statistics import mean

MODEL_VERSION = 'fx-models-2.0.0'


@dataclass(frozen=True)
class Forecast:
    model: str
    status: str
    mean_log_return: float = 0.0
    variance_log_return: float = 0.0
    reason: str = ''
    diagnostics: dict = None

    def to_dict(self):
        value = asdict(self)
        if self.status == 'ready':
            mu, var = self.mean_log_return, self.variance_log_return
            value.update(expected_return=math.expm1(mu + var/2),
                         forecast_sd_return=math.sqrt(math.expm1(var)*math.exp(2*mu+var)),
                         mean_log_return_bps=10000*mu,
                         sd_log_return_bps=10000*math.sqrt(var))
        return value


def unavailable(name, reason):
    return Forecast(name, 'unavailable', reason=reason, diagnostics={})


def variance(xs):
    m = mean(xs)
    return sum((x-m)**2 for x in xs)/max(1, len(xs)-1)


def ou_forecast(prices, horizon, min_bars=64):
    """Discrete OU: OLS AR(1) on log levels; reject nonstationary fits."""
    name = 'ou'
    if len(prices) < min_bars:
        return unavailable(name, 'insufficient_history')
    levels = [math.log(p/prices[0]) for p in prices]
    x, y = levels[:-1], levels[1:]
    mx, my = mean(x), mean(y)
    denom = sum((v-mx)**2 for v in x)
    if denom <= 1e-20:
        return unavailable(name, 'no_price_variation')
    phi = sum((a-mx)*(b-my) for a,b in zip(x,y))/denom
    if not 0 < phi < 0.995:
        return unavailable(name, 'stationarity_not_supported')
    intercept = my-phi*mx
    residual = sum((b-intercept-phi*a)**2 for a,b in zip(x,y))/max(1,len(x)-2)
    if residual <= 1e-20:
        return unavailable(name, 'degenerate_residual_variance')
    equilibrium = intercept/(1-phi)
    mu = equilibrium+(levels[-1]-equilibrium)*phi**horizon-levels[-1]
    var = residual*sum(phi**(2*i) for i in range(horizon))
    return Forecast(name, 'ready', mu, var, diagnostics={
        'phi':phi, 'half_life_bars':-math.log(2)/math.log(phi),
        'equilibrium_log_relative':equilibrium, 'residual_variance':residual,
        'training_bars':len(prices)})


def ar_forecast(prices, horizon, min_bars=64, ridge=1.0):
    """No-intercept AR(1) on returns with fixed dimensionless ridge penalty.

    Unlike OU on price levels, beta may be positive (persistence) or negative
    (return reversal). The forecast shrinks towards the zero-return baseline.
    """
    name = 'return_ar'
    if len(prices) < min_bars:
        return unavailable(name, 'insufficient_history')
    r = [math.log(b/a) for a,b in zip(prices, prices[1:])]
    v = variance(r)
    if v <= 1e-20:
        return unavailable(name, 'no_return_variation')
    x,y = r[:-1],r[1:]
    beta = sum(a*b for a,b in zip(x,y))/(sum(a*a for a in x)+ridge*len(x)*v)
    beta = max(-0.98, min(0.98,beta))
    sigma = sum((b-beta*a)**2 for a,b in zip(x,y))/max(1,len(x)-1)
    if sigma <= 1e-20:
        return unavailable(name, 'degenerate_residual_variance')
    mu = r[-1]*sum(beta**i for i in range(1,horizon+1))
    var = sigma*sum(sum(beta**k for k in range(j+1))**2 for j in range(horizon))
    return Forecast(name,'ready',mu,var,diagnostics={'beta':beta,
        'ridge':ridge,'residual_variance':sigma,'training_bars':len(prices)})


def kalman_forecast(prices, horizon, min_bars=64, damping=0.95,
                    ewma_decay=0.94, q_level=0.05, q_slope=0.005,
                    measurement_noise=0.5):
    """Damped local level/slope Kalman filter with causal EWMA noise scaling.

    Transition: level'=level+slope; slope'=damping*slope. Diagonal process
    noise and measurement noise use the previous return-variance estimate.
    No smoothing, full-sample likelihood fitting or future-state conditioning.
    Fixed variance ratios are research defaults, not calibrated FX parameters.
    """
    name='kalman'
    if len(prices)<min_bars:
        return unavailable(name,'insufficient_history')
    y=[math.log(p/prices[0]) for p in prices]
    returns=[b-a for a,b in zip(y,y[1:])]
    v=variance(returns[:16])
    if v<=1e-20:
        return unavailable(name,'initial_variance_unavailable')
    floor=1e-16
    level,slope=0.0,0.0
    p00,p01,p11=10*v,0.0,v
    def transition(level,slope,p00,p01,p11,v):
        return (level+slope,damping*slope,
                p00+2*p01+p11+q_level*v,
                damping*(p01+p11),damping*damping*p11+q_slope*v)
    for i in range(1,len(y)):
        level,slope,p00,p01,p11=transition(level,slope,p00,p01,p11,v)
        noise=max(floor,measurement_noise*v)
        innovation=y[i]-level
        total=p00+noise
        k0,k1=p00/total,p01/total
        level+=k0*innovation; slope+=k1*innovation
        a,b,c=p00,p01,p11
        p00=max(floor,(1-k0)*a)
        p01=(1-k0)*b
        p11=max(floor,c-k1*b)
        v=max(floor,ewma_decay*v+(1-ewma_decay)*returns[i-1]**2)
    fitted_level,fitted_slope=level,slope
    for _ in range(horizon):
        level,slope,p00,p01,p11=transition(level,slope,p00,p01,p11,v)
    mu=level-y[-1]
    var=max(floor,p00+measurement_noise*v)
    return Forecast(name,'ready',mu,var,diagnostics={
        'filtered_level_log_relative':fitted_level,'filtered_slope':fitted_slope,
        'ewma_return_variance':v,'damping':damping,'training_bars':len(prices),
        'noise_scaling':'causal EWMA; not a latent stochastic-volatility model'})


def forecasts(prices, config):
    args=dict(horizon=config.horizon_bars,min_bars=config.min_bars)
    return [ou_forecast(prices,**args),
            kalman_forecast(prices,**args,damping=config.kalman_damping,
                ewma_decay=config.ewma_decay,q_level=config.q_level,
                q_slope=config.q_slope,measurement_noise=config.measurement_noise),
            ar_forecast(prices,**args,ridge=config.ar_ridge)]
