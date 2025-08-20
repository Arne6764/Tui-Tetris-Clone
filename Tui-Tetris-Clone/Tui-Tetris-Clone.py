#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ASCII/Unicode Tetris — one-window curses TUI, Aquarium Dark vibe
- 10x20 well with double-wide cells to avoid vertical stretching
- 7-bag RNG, SRS kicks (JLSTZ + I), lenient 180° kicks
- Ghost piece, Hold, Next-3 preview
- T-Spin detection (Mini vs Regular), Combo, Back-to-Back scoring
- Simple Finesse metric (inputs vs a baseline)
- Controls: a/d left/right, s soft, w hard, j CCW, k CW, l 180°, space/Shift hold, q quit
"""

import curses
import time
import random

# --- Core dims and look ---
WELL_W, WELL_H = 10, 20
CELL = "██"          # double-wide cell for square-ish aspect
EMPTY = "  "
GHOST = "··"
BORDER_V, BORDER_H = "│", "─"
BORDER_TL, BORDER_TR, BORDER_BL, BORDER_BR = "┌", "┐", "└", "┘"

# Gameplay tuning
TICK_BASE = 0.55          # gravity at level 1 (seconds per row)
SOFT_DROP_MULT = 0.05     # soft drop tick
LOCK_DELAY = 0.5          # lock delay (s)
NEXT_COUNT = 3

# Safe terminal colors (Aquarium Dark-ish vibe)
PIECE_COLOR = {
    'I': curses.COLOR_CYAN,
    'O': curses.COLOR_YELLOW,
    'T': curses.COLOR_MAGENTA,
    'S': curses.COLOR_GREEN,
    'Z': curses.COLOR_RED,
    'J': curses.COLOR_BLUE,
    'L': curses.COLOR_WHITE,
}

# SRS shapes (grid coordinates relative to a piece's origin)
SHAPES = {
    'I': {
        0: [(0,1),(1,1),(2,1),(3,1)],
        1: [(2,0),(2,1),(2,2),(2,3)],
        2: [(0,2),(1,2),(2,2),(3,2)],
        3: [(1,0),(1,1),(1,2),(1,3)],
    },
    'O': {r: [(1,0),(2,0),(1,1),(2,1)] for r in range(4)},
    'T': {
        0: [(1,0),(0,1),(1,1),(2,1)],
        1: [(1,0),(1,1),(2,1),(1,2)],
        2: [(0,1),(1,1),(2,1),(1,2)],
        3: [(1,0),(0,1),(1,1),(1,2)],
    },
    'S': {
        0: [(1,0),(2,0),(0,1),(1,1)],
        1: [(1,0),(1,1),(2,1),(2,2)],
        2: [(1,1),(2,1),(0,2),(1,2)],
        3: [(0,0),(0,1),(1,1),(1,2)],
    },
    'Z': {
        0: [(0,0),(1,0),(1,1),(2,1)],
        1: [(2,0),(1,1),(2,1),(1,2)],
        2: [(0,1),(1,1),(1,2),(2,2)],
        3: [(1,0),(0,1),(1,1),(0,2)],
    },
    'J': {
        0: [(0,0),(0,1),(1,1),(2,1)],
        1: [(1,0),(2,0),(1,1),(1,2)],
        2: [(0,1),(1,1),(2,1),(2,2)],
        3: [(1,0),(1,1),(0,2),(1,2)],
    },
    'L': {
        0: [(2,0),(0,1),(1,1),(2,1)],
        1: [(1,0),(1,1),(1,2),(2,2)],
        2: [(0,1),(1,1),(2,1),(0,2)],
        3: [(0,0),(1,0),(1,1),(1,2)],
    }
}

# SRS kicks
SRS_KICKS = {
    ('JLSTZ', 0, 1): [(0,0), (-1,0), (-1,1), (0,-2), (-1,-2)],
    ('JLSTZ', 1, 0): [(0,0), (1,0), (1,-1), (0,2), (1,2)],
    ('JLSTZ', 1, 2): [(0,0), (1,0), (1,-1), (0,2), (1,2)],
    ('JLSTZ', 2, 1): [(0,0), (-1,0), (-1,1), (0,-2), (-1,-2)],
    ('JLSTZ', 2, 3): [(0,0), (1,0), (1,1), (0,-2), (1,-2)],
    ('JLSTZ', 3, 2): [(0,0), (-1,0), (-1,-1), (0,2), (-1,2)],
    ('JLSTZ', 3, 0): [(0,0), (-1,0), (-1,-1), (0,2), (-1,2)],
    ('JLSTZ', 0, 3): [(0,0), (1,0), (1,1), (0,-2), (1,-2)],
    ('I', 0, 1): [(0,0), (-2,0), (1,0), (-2,-1), (1,2)],
    ('I', 1, 0): [(0,0), (2,0), (-1,0), (2,1), (-1,-2)],
    ('I', 1, 2): [(0,0), (-1,0), (2,0), (-1,2), (2,-1)],
    ('I', 2, 1): [(0,0), (1,0), (-2,0), (1,-2), (-2,1)],
    ('I', 2, 3): [(0,0), (2,0), (-1,0), (2,1), (-1,-2)],
    ('I', 3, 2): [(0,0), (-2,0), (1,0), (-2,-1), (1,2)],
    ('I', 3, 0): [(0,0), (1,0), (-2,0), (1,-2), (-2,1)],
    ('I', 0, 3): [(0,0), (-1,0), (2,0), (-1,2), (2,-1)],
}
KICKS_180 = {
    'I': [(0,0),(1,0),(-1,0),(0,1),(0,-1),(2,0),(-2,0)],
    'O': [(0,0)],
    'JLSTZ': [(0,0),(1,0),(-1,0),(0,1),(0,-1),(2,0),(-2,0),(1,1),(-1,1)]
}

BAG = ['I','O','T','S','Z','J','L']

def rot_index(r, d): return (r + d) % 4

class Piece:
    def __init__(self, kind, x, y):
        self.kind = kind
        self.r = 0
        self.x = x
        self.y = y
    def cells(self, r=None, x=None, y=None):
        r = self.r if r is None else r
        x = self.x if x is None else x
        y = self.y if y is None else y
        return [(x+cx, y+cy) for (cx,cy) in SHAPES[self.kind][r]]

class SevenBag:
    def __init__(self):
        self.q = []
        self.refill()
    def refill(self):
        bag = BAG[:]
        random.shuffle(bag)
        self.q.extend(bag)
    def next(self):
        if len(self.q) < 7: self.refill()
        return self.q.pop(0)

# --- Game state ---
class Game:
    def __init__(self):
        self.board = [[None for _ in range(WELL_W)] for __ in range(WELL_H)]
        self.bag = SevenBag()
        self.hold = None
        self.hold_used = False
        self.score = 0
        self.lines = 0
        self.level = 1
        self.nexts = [self.bag.next() for _ in range(NEXT_COUNT)]
        self.game_over = False
        self.fall_timer = 0.0
        self.lock_timer = 0.0
        self.last_tick = time.time()
        self.b2b = False
        self.combo = -1
        self.last_clear_text = ""
        # Finesse
        self.inputs_this_piece = 0
        self.finesse_faults = 0
        self.finesse_piece_overuses = 0
        # T-Spin helpers
        self.last_action_rotation = False

        self.spawn_new()

    def spawn_new(self, from_hold=False):
        kind = self.hold if from_hold else self.bag.next()
        self.current = Piece(kind, 3, 0)
        self.current.r = 0
        self.hold_used = False
        self.inputs_this_piece = 0
        self.last_action_rotation = False
        if not self.valid(self.current.cells()):
            self.game_over = True

    def valid(self, cells):
        for (x,y) in cells:
            if x < 0 or x >= WELL_W or y < 0 or y >= WELL_H: return False
            if self.board[y][x] is not None: return False
        return True

    def try_move(self, dx, dy, player_input=False):
        c = self.current
        if self.valid(c.cells(x=c.x+dx, y=c.y+dy)):
            c.x += dx; c.y += dy
            if player_input:
                self.inputs_this_piece += 1
                self.last_action_rotation = False
            return True
        return False

    def try_rotate(self, d):
        c = self.current
        fr = c.r
        tr = rot_index(fr, d)
        kind = c.kind

        if d == 2:
            group = 'I' if kind == 'I' else 'JLSTZ'
            for (dx,dy) in KICKS_180[group]:
                if self.valid(c.cells(r=tr, x=c.x+dx, y=c.y+dy)):
                    c.r, c.x, c.y = tr, c.x+dx, c.y+dy
                    self.inputs_this_piece += 1
                    self.last_action_rotation = True
                    return True
            return False

        group = 'I' if kind == 'I' else 'JLSTZ'
        for (dx,dy) in SRS_KICKS.get((group, fr, tr), [(0,0)]):
            if self.valid(c.cells(r=tr, x=c.x+dx, y=c.y+dy)):
                c.r, c.x, c.y = tr, c.x+dx, c.y+dy
                self.inputs_this_piece += 1
                self.last_action_rotation = True
                return True
        return False

    def hard_drop(self):
        dist = 0
        while self.try_move(0, 1):
            dist += 1
        self.score += dist * 2
        self.inputs_this_piece += 1
        self.last_action_rotation = False
        self.lock_piece()

    def soft_drop(self):
        if self.try_move(0, 1, player_input=True):
            self.score += 1

    def on_ground(self):
        return not self.valid(self.current.cells(y=self.current.y+1))

    def lock_piece(self):
        # Place piece
        for (x,y) in self.current.cells():
            if 0 <= y < WELL_H and 0 <= x < WELL_W:
                self.board[y][x] = self.current.kind

        # Detect T-Spin (with piece on board)
        tspin_kind = self.detect_tspin()

        # Clear lines & score
        cleared = self.clear_full_lines()
        self.apply_scoring(cleared, tspin_kind)

        # Finesse (baseline vs used inputs)
        self.update_finesse_stats(final_x=self.current.x, final_r=self.current.r)

        # Next
        self.current = Piece(self.nexts.pop(0), 3, 0)
        self.nexts.append(self.bag.next())
        self.hold_used = False
        self.lock_timer = 0.0
        self.last_action_rotation = False
        self.inputs_this_piece = 0

        if not self.valid(self.current.cells()):
            self.game_over = True

    def clear_full_lines(self):
        new_board, cleared = [], 0
        for row in self.board:
            if all(cell is not None for cell in row):
                cleared += 1
            else:
                new_board.append(row)
        while len(new_board) < WELL_H:
            new_board.insert(0, [None for _ in range(WELL_W)])
        self.board = new_board
        if cleared:
            self.lines += cleared
            self.level = 1 + self.lines // 10
        return cleared

    # --- T-Spin detection (corner + facing rule) ---
    def detect_tspin(self):
        if self.current.kind != 'T' or not self.last_action_rotation:
            return None
        cx, cy = self.current.x + 1, self.current.y + 1

        def filled(x, y):
            if x < 0 or x >= WELL_W or y < 0 or y >= WELL_H:
                return True
            return self.board[y][x] is not None

        corners = [(cx-1,cy-1),(cx+1,cy-1),(cx-1,cy+1),(cx+1,cy+1)]
        filled_count = sum(1 for (x,y) in corners if filled(x,y))

        r = self.current.r
        if r == 0:     front = [(cx-1,cy-1),(cx+1,cy-1)]
        elif r == 1:   front = [(cx+1,cy-1),(cx+1,cy+1)]
        elif r == 2:   front = [(cx-1,cy+1),(cx+1,cy+1)]
        else:          front = [(cx-1,cy-1),(cx-1,cy+1)]
        front_filled = sum(1 for (x,y) in front if filled(x,y))

        if filled_count >= 4:
            return 'T'
        if filled_count == 3:
            return 'Mini' if front_filled < 2 else 'T'
        return None

    # --- Scoring (simplified guideline-like) ---
    def apply_scoring(self, cleared, tspin_kind):
        base, b2b_ok, text = 0, False, ""

        if tspin_kind is None:
            if cleared == 1: base = 100; text = "Single"
            elif cleared == 2: base = 300; text = "Double"
            elif cleared == 3: base = 500; text = "Triple"
            elif cleared == 4: base = 800; text = "Tetris"; b2b_ok = True
        else:
            if tspin_kind == 'Mini':
                if cleared == 0: base = 100; text = "T-Spin Mini"
                elif cleared == 1: base = 200; text = "T-Spin Mini Single"; b2b_ok = True
                else: tspin_kind = 'T'  # minis clearing >1 are treated as regular here
            if tspin_kind == 'T':
                if cleared == 0: base = 400; text = "T-Spin"
                elif cleared == 1: base = 800; text = "T-Spin Single"; b2b_ok = True
                elif cleared == 2: base = 1200; text = "T-Spin Double"; b2b_ok = True
                elif cleared == 3: base = 1600; text = "T-Spin Triple"; b2b_ok = True

        if cleared > 0:
            if b2b_ok:
                if self.b2b: base += base // 2
                self.b2b = True
            else:
                self.b2b = False

            self.combo += 1
            if self.combo >= 1:
                base += 50 * self.combo
        else:
            self.combo = -1

        self.score += base
        self.last_clear_text = text if (cleared > 0 or tspin_kind) else ""

    # --- Finesse (very simple baseline) ---
    def update_finesse_stats(self, final_x, final_r):
        spawn_x, spawn_r = 3, 0
        rot_delta = (final_r - spawn_r) % 4
        min_rot = min(rot_delta, 4 - rot_delta)
        if rot_delta == 2: min_rot = 1   # 180 key exists
        min_horiz = abs(final_x - spawn_x)
        min_inputs = min_horiz + min_rot + 1  # +1 for (hard) drop/confirm
        if self.inputs_this_piece > min_inputs:
            self.finesse_faults += (self.inputs_this_piece - min_inputs)
            self.finesse_piece_overuses += 1

    def ghost_y(self):
        c = self.current
        gy = c.y
        while self.valid(c.cells(y=gy+1)):
            gy += 1
        return gy

    def hold_piece(self):
        if self.hold_used: return
        if self.hold is None:
            self.hold = self.current.kind
            self.current = Piece(self.nexts.pop(0), 3, 0)
            self.nexts.append(self.bag.next())
        else:
            self.hold, self.current = self.current.kind, Piece(self.hold, 3, 0)
        self.current.r = 0
        self.hold_used = True
        self.inputs_this_piece = 0
        self.last_action_rotation = False
        if not self.valid(self.current.cells()):
            self.game_over = True

    def update(self, soft_drop=False):
        now = time.time()
        dt = now - self.last_tick
        self.last_tick = now
        self.fall_timer += dt

        grav = max(0.06, TICK_BASE * (0.87 ** (self.level-1)))
        if soft_drop:
            grav = SOFT_DROP_MULT

        while self.fall_timer >= grav and not self.game_over:
            self.fall_timer -= grav
            if not self.try_move(0,1):
                self.lock_timer += grav
                if self.lock_timer >= LOCK_DELAY:
                    self.lock_piece()
                    break
            else:
                self.lock_timer = 0.0

# --- Curses UI helpers ---
def safe_addstr(stdscr, y, x, s, attr=0):
    try:
        stdscr.addstr(y, x, s, attr)
    except curses.error:
        pass

def init_colors():
    curses.start_color()
    curses.use_default_colors()
    # piece colors
    color_map = {}
    pair = 1
    for k, fg in PIECE_COLOR.items():
        curses.init_pair(pair, fg, -1)
        color_map[k] = pair
        pair += 1
    curses.init_pair(pair, curses.COLOR_WHITE, -1); ghost_pair = pair; pair += 1
    curses.init_pair(pair, curses.COLOR_CYAN, -1); ui_pair = pair; pair += 1
    curses.init_pair(pair, curses.COLOR_BLUE, -1); border_pair = pair
    return color_map, ghost_pair, ui_pair, border_pair

def draw_border(stdscr, x, y, w, h, color):
    safe_addstr(stdscr, y,   x, BORDER_TL + BORDER_H*(w-2) + BORDER_TR, curses.color_pair(color))
    for r in range(1,h-1):
        safe_addstr(stdscr, y+r, x, BORDER_V, curses.color_pair(color))
        safe_addstr(stdscr, y+r, x+w-1, BORDER_V, curses.color_pair(color))
    safe_addstr(stdscr, y+h-1, x, BORDER_BL + BORDER_H*(w-2) + BORDER_BR, curses.color_pair(color))

def draw_mini_piece(stdscr, kind, x, y, colors):
    shape = SHAPES[kind][0]
    minx = min(px for px,py in shape); miny = min(py for px,py in shape)
    for (px,py) in shape:
        sx = x + (px - minx)*2
        sy = y + (py - miny)
        safe_addstr(stdscr, sy, sx, CELL, curses.color_pair(colors[kind]))

def compute_layout(stdscr):
    H, W = stdscr.getmaxyx()
    board_char_w = WELL_W*2
    play_w = board_char_w + 2             # +2 for vertical borders
    play_h = WELL_H + 2                   # +2 for horizontal borders
    next_w = 16                           # enough for mini pieces with double width
    hold_w = 16
    gap = 2

    # Offset so the hold panel fits entirely to the left
    w_off = hold_w + 4
    h_off = 2

    total_w = w_off + play_w + gap + next_w + 2
    total_h = h_off + play_h + 2

    return {
        "H": H, "W": W,
        "play_w": play_w, "play_h": play_h,
        "next_w": next_w, "hold_w": hold_w, "gap": gap,
        "w_off": w_off, "h_off": h_off,
        "min_W": total_w, "min_H": total_h
    }

def render(stdscr, game, colors, ghost_pair, ui_pair, border_pair):
    stdscr.erase()
    L = compute_layout(stdscr)
    if L["W"] < L["min_W"] or L["H"] < L["min_H"]:
        msg = f" Resize terminal to at least {L['min_W']}×{L['min_H']} (cols×rows) "
        safe_addstr(stdscr, max(0, L["H"]//2), max(0, (L["W"]-len(msg))//2), msg, curses.A_BOLD)
        stdscr.refresh(); return

    w_off, h_off = L["w_off"], L["h_off"]
    play_w, play_h = L["play_w"], L["play_h"]
    next_w, hold_w, gap = L["next_w"], L["hold_w"], L["gap"]
    board_char_w = WELL_W*2

    # Panel anchors
    next_x = w_off + play_w + gap
    next_y = h_off
    hold_x = w_off - (hold_w + 2)
    hold_y = h_off

    # Borders
    draw_border(stdscr, w_off, h_off, play_w, play_h, border_pair)
    draw_border(stdscr, next_x, next_y, next_w, play_h//2, border_pair)
    draw_border(stdscr, next_x, next_y + play_h//2 + 1, next_w, play_h - (play_h//2) - 1, border_pair)
    draw_border(stdscr, hold_x, hold_y, hold_w, 8, border_pair)
    draw_border(stdscr, hold_x, hold_y + 9, hold_w, 9, border_pair)

    # Titles
    safe_addstr(stdscr, h_off-1, w_off, " ASCII TETRIS — Aquarium Dark ", curses.color_pair(ui_pair))
    safe_addstr(stdscr, hold_y, hold_x + 2, " HOLD ", curses.color_pair(ui_pair))
    safe_addstr(stdscr, next_y, next_x + 2, " NEXT ", curses.color_pair(ui_pair))
    safe_addstr(stdscr, next_y + play_h//2 + 1, next_x + 2, " INFO ", curses.color_pair(ui_pair))

    # Board cells
    for y in range(WELL_H):
        for x in range(WELL_W):
            cell = game.board[y][x]
            ch = CELL if cell else EMPTY
            attr = curses.color_pair(colors[cell]) if cell else 0
            safe_addstr(stdscr, h_off+1+y, w_off+1 + x*2, ch, attr)

    # Ghost
    gy = game.ghost_y()
    for (x,y) in game.current.cells(y=gy):
        if 0 <= y < WELL_H and 0 <= x < WELL_W:
            safe_addstr(stdscr, h_off+1+y, w_off+1 + x*2, GHOST, curses.color_pair(ghost_pair) | curses.A_DIM)

    # Current
    k = game.current.kind
    for (x,y) in game.current.cells():
        if 0 <= y < WELL_H and 0 <= x < WELL_W:
            safe_addstr(stdscr, h_off+1+y, w_off+1 + x*2, CELL, curses.color_pair(colors[k]))

    # Hold piece
    if game.hold:
        draw_mini_piece(stdscr, game.hold, hold_x+3, hold_y+3, colors)

    # Next (3)
    for i,kind in enumerate(game.nexts[:NEXT_COUNT]):
        draw_mini_piece(stdscr, kind, next_x+2, next_y + 2 + i*6, colors)

    # Info panel (scoreline + meta)
    ix = next_x + 2
    iy = next_y + play_h//2 + 2
    safe_addstr(stdscr, iy,     ix, f"Score: {game.score}", curses.color_pair(ui_pair))
    safe_addstr(stdscr, iy + 1, ix, f"Lines: {game.lines}", curses.color_pair(ui_pair))
    safe_addstr(stdscr, iy + 2, ix, f"Level: {game.level}", curses.color_pair(ui_pair))
    safe_addstr(stdscr, iy + 3, ix, f"B2B: {'ON' if game.b2b else 'off'}", curses.color_pair(ui_pair))
    safe_addstr(stdscr, iy + 4, ix, f"Combo: {max(game.combo, -1)}", curses.color_pair(ui_pair))
    safe_addstr(stdscr, iy + 5, ix, f"Finesse faults: {game.finesse_faults}", curses.color_pair(ui_pair))
    safe_addstr(stdscr, iy + 6, ix, f"Pieces overused: {game.finesse_piece_overuses}", curses.color_pair(ui_pair))
    if game.last_clear_text:
        safe_addstr(stdscr, iy + 7, ix, f"Last: {game.last_clear_text}", curses.color_pair(ui_pair))

    # Controls hint (bottom of info)
    hints = ["a/d=move", "s=soft", "w=hard", "j/k=⟲/⟳", "l=180°", "space=Hold", "q=Quit"]
    for i,h in enumerate(hints):
        safe_addstr(stdscr, iy + 9 + i, ix, h, curses.color_pair(ui_pair))

    if game.game_over:
        msg = "  GAME OVER — press q  "
        safe_addstr(stdscr, h_off + (play_h//2), w_off + max(1, (play_w - len(msg))//2), msg, curses.A_BOLD)

    stdscr.refresh()

# --- Main loop ---
def main(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(0)

    colors, ghost_pair, ui_pair, border_pair = init_colors()
    g = Game()

    soft_drop = False
    last_frame = time.time()

    while True:
        # Input (drain buffer)
        ch = stdscr.getch()
        while ch != -1:
            if ch in (ord('q'), ord('Q')):
                return
            if g.game_over:
                ch = stdscr.getch(); continue

            if ch in (ord('a'), ord('A')):
                g.try_move(-1, 0, player_input=True); g.lock_timer = 0.0
            elif ch in (ord('d'), ord('D')):
                g.try_move(1, 0, player_input=True); g.lock_timer = 0.0
            elif ch in (ord('s'), ord('S')):
                g.soft_drop(); soft_drop = True
            elif ch in (ord('w'), ord('W')):
                g.hard_drop()
            elif ch in (ord('j'), ord('J')):
                if g.try_rotate(-1): g.lock_timer = 0.0
            elif ch in (ord('k'), ord('K')):
                if g.try_rotate(+1): g.lock_timer = 0.0
            elif ch in (ord('l'), ord('L')):
                if g.try_rotate(+2): g.lock_timer = 0.0
            elif ch in (ord(' '),):  # Shift+Space also comes through as space on most terminals
                g.hold_piece(); g.lock_timer = 0.0

            ch = stdscr.getch()

        # Update world
        g.update(soft_drop=soft_drop)
        soft_drop = False

        # Render
        render(stdscr, g, colors, ghost_pair, ui_pair, border_pair)

        # Frame pacing
        now = time.time()
        dt = now - last_frame
        if dt < 0.01:
            time.sleep(0.01 - dt)
        last_frame = now

if __name__ == "__main__":
    curses.wrapper(main)
