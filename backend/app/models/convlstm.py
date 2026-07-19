"""
ConvLSTM forecaster (Step 5) — feature cubes as video frames, per the
PM2.5-GNN / ForecastPro reference pattern: convolutions capture per-timestep
spatial structure, LSTM gating captures temporal evolution.

Input:  (B, T, C, H, W) — sliding window of T hourly cubes
Output: (B, H, W)       — predicted PM2.5 grid one step ahead; longer
                          horizons come from autoregressive rollout in
                          inference.py, feeding predictions back in.
"""

import torch
import torch.nn as nn


class ConvLSTMCell(nn.Module):
    def __init__(self, in_channels: int, hidden_channels: int, kernel_size: int = 3):
        super().__init__()
        padding = kernel_size // 2
        self.hidden_channels = hidden_channels
        self.conv = nn.Conv2d(
            in_channels + hidden_channels, 4 * hidden_channels, kernel_size, padding=padding
        )

    def forward(self, x, state):
        h, c = state
        gates = self.conv(torch.cat([x, h], dim=1))
        i, f, o, g = torch.chunk(gates, 4, dim=1)
        i, f, o = torch.sigmoid(i), torch.sigmoid(f), torch.sigmoid(o)
        g = torch.tanh(g)
        c = f * c + i * g
        h = o * torch.tanh(c)
        return h, c

    def init_state(self, batch: int, height: int, width: int, device):
        shape = (batch, self.hidden_channels, height, width)
        return torch.zeros(shape, device=device), torch.zeros(shape, device=device)


class ConvLSTMForecaster(nn.Module):
    def __init__(self, in_channels: int, hidden_channels: int = 32, num_layers: int = 2):
        super().__init__()
        self.cells = nn.ModuleList(
            [
                ConvLSTMCell(in_channels if i == 0 else hidden_channels, hidden_channels)
                for i in range(num_layers)
            ]
        )
        self.head = nn.Conv2d(hidden_channels, 1, kernel_size=1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (B, T, C, H, W)
        b, t, _, h, w = x.shape
        states = [cell.init_state(b, h, w, x.device) for cell in self.cells]
        for step in range(t):
            inp = x[:, step]
            for i, cell in enumerate(self.cells):
                states[i] = cell(inp, states[i])
                inp = states[i][0]
        return self.head(states[-1][0]).squeeze(1)  # (B, H, W)
