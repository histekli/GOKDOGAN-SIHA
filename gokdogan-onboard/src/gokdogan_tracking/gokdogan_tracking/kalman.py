"""Sabit-ivme Kalman filtresi (SAD §10). Durum [px,py,vx,vy,ax,ay], ölçüm [px,py].

Piksel uzayında (1920×1200) hedef merkezi takibi. Saf numpy — test edilebilir.
"""
import numpy as np


class KalmanBoxState:
    def __init__(self, px, py, q=1.0, r=4.0):
        # Durum: [px, py, vx, vy, ax, ay]
        self.x = np.array([px, py, 0.0, 0.0, 0.0, 0.0], dtype=float)
        self.P = np.eye(6) * 100.0
        self._q = q      # süreç gürültüsü ölçeği
        self._r = r      # ölçüm gürültüsü (piksel²)
        # Ölçüm matrisi: sadece konum gözlemlenir
        self.H = np.zeros((2, 6))
        self.H[0, 0] = 1.0
        self.H[1, 1] = 1.0
        self.R = np.eye(2) * r

    @staticmethod
    def _F(dt):
        F = np.eye(6)
        F[0, 2] = dt
        F[1, 3] = dt
        F[0, 4] = 0.5 * dt * dt
        F[1, 5] = 0.5 * dt * dt
        F[2, 4] = dt
        F[3, 5] = dt
        return F

    def _Q(self, dt):
        # Sabit-ivme süreç gürültüsü (basitleştirilmiş, ivme sürücülü)
        q = self._q
        G = np.array([0.5 * dt * dt, 0.5 * dt * dt, dt, dt, 1.0, 1.0])
        return np.outer(G, G) * q

    def predict(self, dt):
        F = self._F(dt)
        self.x = F @ self.x
        self.P = F @ self.P @ F.T + self._Q(dt)
        return self.x[:2].copy()

    def update(self, px, py):
        z = np.array([px, py], dtype=float)
        y = z - self.H @ self.x
        S = self.H @ self.P @ self.H.T + self.R
        K = self.P @ self.H.T @ np.linalg.inv(S)
        self.x = self.x + K @ y
        self.P = (np.eye(6) - K @ self.H) @ self.P
        return self.x[:2].copy()

    @property
    def pos(self):
        return float(self.x[0]), float(self.x[1])

    @property
    def vel(self):
        return float(self.x[2]), float(self.x[3])
