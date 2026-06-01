from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from typing import List


SIGMA = 5.670374419e-8


@dataclass
class BilletSpec:
    width_m: float
    thickness_m: float
    length_m: float
    density: float
    cp: float
    conductivity: float
    emissivity: float
    initial_temp_c: float
    target_discharge_temp_c: float
    max_surface_core_delta_c: float
    max_heating_rate_c_per_min: float


@dataclass
class Zone:
    name: str
    length_m: float
    setpoint_c: float
    htc_w_m2k: float


@dataclass
class FurnaceConfig:
    zones: List[Zone]
    walking_step_m: float
    step_period_s: float


@dataclass
class ZoneSnapshot:
    zone_name: str
    zone_setpoint_c: float
    residence_time_s: float
    exit_surface_temp_c: float
    exit_core_temp_c: float
    exit_average_temp_c: float
    average_heating_rate_c_per_min: float
    target_average_temp_c: float


@dataclass
class SimulationResult:
    final_surface_temp_c: float
    final_core_temp_c: float
    final_average_temp_c: float
    discharge_temp_error_c: float
    surface_core_delta_c: float
    max_heating_rate_c_per_min: float
    fuel_proxy: float
    oxidation_proxy: float
    heating_rate_penalty: float
    soaking_penalty: float
    objective: float
    zone_setpoints_c: List[float]
    zone_snapshots: List[ZoneSnapshot]
    ideal_profile_c: List[float]
    temperature_profile_c: List[float]


class WalkingBeamLevel2OfflineModel:
    def __init__(self, billet: BilletSpec, furnace: FurnaceConfig, grid_points: int = 25):
        if grid_points < 5 or grid_points % 2 == 0:
            raise ValueError("grid_points must be an odd number >= 5")
        self.billet = billet
        self.furnace = furnace
        self.grid_points = grid_points

    def simulate(self, zone_setpoints: List[float] | None = None) -> SimulationResult:
        zones = self._with_setpoints(zone_setpoints)
        temperatures = [self.billet.initial_temp_c for _ in range(self.grid_points)]
        dx = (self.billet.thickness_m / 2.0) / (self.grid_points - 1)
        dt = self._stable_dt(dx)
        line_speed = self._line_speed_m_per_s()
        total_time_s = sum(zone.length_m / line_speed for zone in zones)
        ideal_profile = self._ideal_average_temperature_profile(zones, total_time_s)
        snapshots: List[ZoneSnapshot] = []

        elapsed_s = 0.0
        last_avg = self.billet.initial_temp_c
        max_heating_rate = 0.0

        for index, zone in enumerate(zones):
            residence_s = zone.length_m / line_speed
            steps = max(1, math.ceil(residence_s / dt))
            actual_dt = residence_s / steps
            for _ in range(steps):
                temperatures = self._step_temperature(temperatures, zone.setpoint_c, zone.htc_w_m2k, dx, actual_dt)
            elapsed_s += residence_s
            average_temp = self._average(temperatures)
            heating_rate = (average_temp - last_avg) / max(residence_s / 60.0, 1e-9)
            max_heating_rate = max(max_heating_rate, heating_rate)
            snapshots.append(
                ZoneSnapshot(
                    zone_name=zone.name,
                    zone_setpoint_c=zone.setpoint_c,
                    residence_time_s=residence_s,
                    exit_surface_temp_c=temperatures[0],
                    exit_core_temp_c=temperatures[-1],
                    exit_average_temp_c=average_temp,
                    average_heating_rate_c_per_min=heating_rate,
                    target_average_temp_c=ideal_profile[index],
                )
            )
            last_avg = average_temp

        final_surface = temperatures[0]
        final_core = temperatures[-1]
        final_avg = self._average(temperatures)
        discharge_error = final_avg - self.billet.target_discharge_temp_c
        surface_core_delta = abs(final_surface - final_core)
        fuel_proxy = self._fuel_proxy(zones)
        oxidation_proxy = self._oxidation_proxy(zones, temperatures)
        heating_rate_penalty = max(0.0, max_heating_rate - self.billet.max_heating_rate_c_per_min) ** 2
        soaking_penalty = sum((snap.exit_average_temp_c - snap.target_average_temp_c) ** 2 for snap in snapshots)

        objective = (
            15.0 * discharge_error ** 2
            + 5.0 * max(0.0, surface_core_delta - self.billet.max_surface_core_delta_c) ** 2
            + 4.0 * heating_rate_penalty
            + 1.0 * soaking_penalty
            + 0.20 * fuel_proxy
            + 0.50 * oxidation_proxy
        )

        return SimulationResult(
            final_surface_temp_c=final_surface,
            final_core_temp_c=final_core,
            final_average_temp_c=final_avg,
            discharge_temp_error_c=discharge_error,
            surface_core_delta_c=surface_core_delta,
            max_heating_rate_c_per_min=max_heating_rate,
            fuel_proxy=fuel_proxy,
            oxidation_proxy=oxidation_proxy,
            heating_rate_penalty=heating_rate_penalty,
            soaking_penalty=soaking_penalty,
            objective=objective,
            zone_setpoints_c=[zone.setpoint_c for zone in zones],
            zone_snapshots=snapshots,
            ideal_profile_c=ideal_profile,
            temperature_profile_c=temperatures,
        )

    def optimize(self, iterations: int = 24, search_span_c: float = 60.0, step_c: float = 10.0) -> SimulationResult:
        current = [zone.setpoint_c for zone in self.furnace.zones]
        best = self.simulate(current)
        local_span = search_span_c
        local_step = step_c

        for _ in range(iterations):
            improved = False
            for index in range(len(current)):
                candidates = self._candidate_values(current[index], local_span, local_step)
                best_local_vector = current
                best_local_result = best
                for candidate in candidates:
                    proposal = current[:]
                    proposal[index] = self._bounded_setpoint(proposal, index, candidate)
                    if not self._is_reasonable_profile(proposal):
                        continue
                    result = self.simulate(proposal)
                    if result.objective + 1e-9 < best_local_result.objective:
                        best_local_result = result
                        best_local_vector = proposal
                if best_local_result.objective + 1e-9 < best.objective:
                    best = best_local_result
                    current = best_local_vector
                    improved = True
            if not improved:
                if local_step <= 2.0:
                    break
                local_span = max(8.0, local_span / 2.0)
                local_step = max(2.0, local_step / 2.0)

        return best

    def _step_temperature(self, temps_c: List[float], furnace_temp_c: float, htc: float, dx: float, dt: float) -> List[float]:
        new_temps = temps_c[:]
        center = self.grid_points - 1

        for i in range(1, self.grid_points - 1):
            alpha = self._thermal_diffusivity(temps_c[i])
            laplace = (temps_c[i - 1] - 2.0 * temps_c[i] + temps_c[i + 1]) / (dx * dx)
            new_temps[i] = temps_c[i] + alpha * dt * laplace

        center_alpha = self._thermal_diffusivity(temps_c[center])
        new_temps[center] = temps_c[center] + center_alpha * dt * 2.0 * (temps_c[center - 1] - temps_c[center]) / (dx * dx)

        surface_temp_c = temps_c[0]
        surface_k = surface_temp_c + 273.15
        furnace_k = furnace_temp_c + 273.15
        k_surface = self._conductivity(surface_temp_c)
        rho = self._density(surface_temp_c)
        cp = self._cp(surface_temp_c)
        q_conv = htc * (furnace_k - surface_k)
        q_rad = self.billet.emissivity * SIGMA * (furnace_k ** 4 - surface_k ** 4)
        q_total = q_conv + q_rad
        conduction_term = 2.0 * k_surface * (temps_c[1] - temps_c[0]) / (dx * dx)
        source_term = 2.0 * q_total / dx
        new_temps[0] = temps_c[0] + dt * (conduction_term + source_term) / (rho * cp)

        return new_temps

    def _stable_dt(self, dx: float) -> float:
        alpha_max = self._thermal_diffusivity(1250.0)
        return min(0.2, 0.35 * dx * dx / max(alpha_max, 1e-12))

    def _density(self, temp_c: float) -> float:
        return self.billet.density

    def _cp(self, temp_c: float) -> float:
        return self.billet.cp + 0.18 * max(0.0, temp_c - 20.0)

    def _conductivity(self, temp_c: float) -> float:
        return max(18.0, self.billet.conductivity - 0.010 * max(0.0, temp_c - 20.0))

    def _thermal_diffusivity(self, temp_c: float) -> float:
        return self._conductivity(temp_c) / (self._density(temp_c) * self._cp(temp_c))

    def _ideal_average_temperature_profile(self, zones: List[Zone], total_time_s: float) -> List[float]:
        total_rise = self.billet.target_discharge_temp_c - self.billet.initial_temp_c
        weighted_lengths = []
        for zone in zones:
            name = zone.name.lower()
            factor = 0.18
            if "preheat" in name:
                factor = 0.14
            elif "heat" in name:
                factor = 0.32
            elif "soak" in name:
                factor = 0.22
            weighted_lengths.append(zone.length_m * factor)
        total_weight = sum(weighted_lengths)

        profile = []
        cumulative = self.billet.initial_temp_c
        for index, zone in enumerate(zones):
            rise = total_rise * weighted_lengths[index] / max(total_weight, 1e-9)
            cumulative += rise
            if index == len(zones) - 1:
                cumulative = self.billet.target_discharge_temp_c
            profile.append(cumulative)
        return profile

    def _fuel_proxy(self, zones: List[Zone]) -> float:
        ambient = 25.0
        return sum(zone.length_m * max(0.0, zone.setpoint_c - ambient) ** 1.05 for zone in zones)

    def _oxidation_proxy(self, zones: List[Zone], final_profile_c: List[float]) -> float:
        high_temp_cost = sum(zone.length_m * max(0.0, zone.setpoint_c - 1180.0) ** 1.15 for zone in zones)
        hot_surface_cost = max(0.0, final_profile_c[0] - 1200.0) ** 2
        return high_temp_cost + hot_surface_cost

    def _line_speed_m_per_s(self) -> float:
        return self.furnace.walking_step_m / self.furnace.step_period_s

    def _average(self, values: List[float]) -> float:
        return sum(values) / len(values)

    def _with_setpoints(self, zone_setpoints: List[float] | None) -> List[Zone]:
        if zone_setpoints is None:
            return self.furnace.zones
        if len(zone_setpoints) != len(self.furnace.zones):
            raise ValueError("zone_setpoints length mismatch")
        return [
            Zone(
                name=zone.name,
                length_m=zone.length_m,
                setpoint_c=zone_setpoints[index],
                htc_w_m2k=zone.htc_w_m2k,
            )
            for index, zone in enumerate(self.furnace.zones)
        ]

    def _candidate_values(self, base: float, span: float, step: float) -> List[float]:
        values = []
        x = base - span
        while x <= base + span + 1e-9:
            values.append(round(x, 6))
            x += step
        values.append(base)
        return sorted(set(values))

    def _bounded_setpoint(self, proposal: List[float], index: int, candidate: float) -> float:
        lower = 760.0
        upper = 1320.0
        if index > 0:
            lower = max(lower, proposal[index - 1] + 20.0)
        if index < len(proposal) - 1:
            upper = min(upper, proposal[index + 1] + 40.0)
        return max(lower, min(candidate, upper))

    def _is_reasonable_profile(self, values: List[float]) -> bool:
        for left, right in zip(values, values[1:]):
            if right < left - 10.0:
                return False
            if right - left > 260.0:
                return False
        return True


def load_case(path: str) -> tuple[BilletSpec, FurnaceConfig]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    billet = BilletSpec(**data["billet"])
    furnace = FurnaceConfig(
        zones=[Zone(**zone) for zone in data["furnace"]["zones"]],
        walking_step_m=data["furnace"]["walking_step_m"],
        step_period_s=data["furnace"]["step_period_s"],
    )
    return billet, furnace


def result_to_dict(result: SimulationResult) -> dict:
    return asdict(result)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Walking-beam furnace level-2 offline model")
    parser.add_argument("case", help="Path to the JSON case file")
    parser.add_argument("--mode", choices=["simulate", "optimize"], default="optimize")
    parser.add_argument("--iterations", type=int, default=24)
    parser.add_argument("--search-span", type=float, default=60.0)
    parser.add_argument("--step", type=float, default=10.0)
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    billet, furnace = load_case(args.case)
    model = WalkingBeamLevel2OfflineModel(billet, furnace)

    if args.mode == "simulate":
        result = model.simulate()
    else:
        result = model.optimize(iterations=args.iterations, search_span_c=args.search_span, step_c=args.step)

    print(json.dumps(result_to_dict(result), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
