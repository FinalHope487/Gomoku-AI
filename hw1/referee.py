import argparse
import sys
import time
import queue
import random
import threading
import subprocess
import unicodedata
from statistics import mean

from common import (
    BLACK, WHITE,
    opponent, create_board, board_full,
    is_legal_move, is_win_after_move, legal_moves
)

BOARD_SIZE = 15
MOVE_TIMEOUT_SEC = 5.0
COLUMN_LABELS = [chr(ord("A") + i) for i in range(BOARD_SIZE)]
EMPTY_CELL = "・"
CELL_WIDTH = 2

WHITE_MARKERS = [None]
WHITE_MARKERS.extend(chr(cp) for cp in range(0x2776, 0x2780))  # ❶..❿
WHITE_MARKERS.extend(chr(cp) for cp in range(0x24EB, 0x24F5))  # ⓫..⓴

BLACK_MARKERS = [None]
BLACK_MARKERS.extend(chr(cp) for cp in range(0x2460, 0x2474))  # ①..⑳

# 使用者目前偏好的 21 手後棋子樣式：黑〇、白𒊹
# 空位改用全形中點，讓棋盤視覺上確實維持固定雙欄寬。
BLACK_PLAIN_MARKER = "〇"
WHITE_PLAIN_MARKER = "𒊹"
# 在 CJK 終端機中，帶圈數字與幾何符號常被視為寬字元；
# 把 Ambiguous 類別也當成雙欄可減少欄位錯位。
AMBIGUOUS_IS_WIDE = True


MANUAL_WIDE_CHARS = {
    # 空位在你的終端看起來是雙欄，保留為 2。
    "・": 2,
    # 黑方 21 手後的 〇 在你的終端看起來較接近雙欄。
    "〇": 2,
    # 白方 21 手後的 𒊹 以及前 20 手圈號，在你的終端更像單欄；
    # 這裡把它們當成 1，pad_cell 會自動補到固定雙欄。
    "𒊹": 1,
}
for ch in BLACK_MARKERS[1:]:
    MANUAL_WIDE_CHARS[ch] = 1
for ch in WHITE_MARKERS[1:]:
    MANUAL_WIDE_CHARS[ch] = 1

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--black", required=True, help="black engine py file")
    p.add_argument("--white", required=True, help="white engine py file")
    return p.parse_args()

def char_display_width(ch: str) -> int:
    if not ch:
        return 0
    if ch in MANUAL_WIDE_CHARS:
        return MANUAL_WIDE_CHARS[ch]
    if unicodedata.combining(ch):
        return 0
    east = unicodedata.east_asian_width(ch)
    if east in ("F", "W"):
        return 2
    if AMBIGUOUS_IS_WIDE and east == "A":
        return 2
    return 1


def text_display_width(text: str) -> int:
    return sum(char_display_width(ch) for ch in text)


def pad_cell(text: str, width: int) -> str:
    return text + (" " * max(0, width - text_display_width(text)))


def board_cell_width() -> int:
    return CELL_WIDTH


def send_line(proc, msg: str):
    proc.stdin.write(msg + "\n")
    proc.stdin.flush()


def safe_send_end(proc, result: str):
    try:
        send_line(proc, f"END {result}")
    except Exception:
        pass


def send_turn(proc, board):
    send_line(proc, "TURN")
    send_line(proc, "BOARD")
    for row in board:
        send_line(proc, " ".join(map(str, row)))
    send_line(proc, "END_BOARD")


def recv_line_with_timeout(proc, timeout_sec: float) -> str:
    q = queue.Queue()

    def _reader():
        try:
            line = proc.stdout.readline()
            q.put(line)
        except Exception as e:
            q.put(e)

    t = threading.Thread(target=_reader, daemon=True)
    t.start()

    try:
        item = q.get(timeout=timeout_sec)
    except queue.Empty:
        raise TimeoutError(f"engine timeout after {timeout_sec} sec")

    if isinstance(item, Exception):
        raise item

    if not item:
        raise RuntimeError("engine disconnected")

    return item.strip()


def parse_move(line: str):
    parts = line.split()
    if len(parts) != 3 or parts[0] != "MOVE":
        raise ValueError(f"invalid engine response: {line}")
    x = int(parts[1])
    y = int(parts[2])
    return x, y


def launch_engine(cmd):
    return subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=None,
        text=True,
        bufsize=1
    )


def coord_to_label(x: int, y: int) -> str:
    return f"{COLUMN_LABELS[x]}{y + 1}"


def move_marker(color: int, side_move_index: int) -> str:
    if color == BLACK:
        if side_move_index < len(BLACK_MARKERS):
            return BLACK_MARKERS[side_move_index]
        return BLACK_PLAIN_MARKER

    if side_move_index < len(WHITE_MARKERS):
        return WHITE_MARKERS[side_move_index]
    return WHITE_PLAIN_MARKER


def format_board_with_move_index(board, move_index_board) -> str:
    cell_width = board_cell_width()
    header_cells = [pad_cell(label, cell_width) for label in COLUMN_LABELS]
    header = "   " + "".join(header_cells)
    lines = [header]

    for y, row in enumerate(board):
        rendered = []
        for x, color in enumerate(row):
            if color == BLACK:
                token = move_marker(BLACK, move_index_board[y][x])
            elif color == WHITE:
                token = move_marker(WHITE, move_index_board[y][x])
            else:
                token = EMPTY_CELL
            rendered.append(pad_cell(token, cell_width))
        lines.append(f"{y + 1:>2} " + "".join(rendered))

    return "\n".join(lines)


def empty_move_index_board(size: int):
    return [[0] * size for _ in range(size)]


def init_stats():
    return {
        BLACK: {"times": [], "max": 0.0, "timeouts": 0},
        WHITE: {"times": [], "max": 0.0, "timeouts": 0},
    }


def record_timing(stats, color: int, elapsed: float, timed_out: bool):
    stats[color]["times"].append(elapsed)
    stats[color]["max"] = max(stats[color]["max"], elapsed)
    if timed_out:
        stats[color]["timeouts"] += 1


def calc_white_score(white_result: str, white_move_count: int, white_times) -> float:
    avg_time_1dp = round(mean(white_times), 1) if white_times else 0.0
    if white_result == "WIN":
        return 234 - white_move_count - avg_time_1dp
    if white_result == "DRAW":
        return 117 - avg_time_1dp
    return white_move_count - avg_time_1dp


def print_match_stats(stats, move_sequence, side_move_counts, white_result: str):
    print("\n=== Match timing summary ===")
    for color, name in ((BLACK, "BLACK"), (WHITE, "WHITE")):
        times = stats[color]["times"]
        avg_time = mean(times) if times else 0.0
        max_time = stats[color]["max"]
        timeout_count = stats[color]["timeouts"]
        print(
            f"{name}: avg={avg_time:.3f}s, "
            f"max single move={max_time:.3f}s, "
            f"timeouts>{MOVE_TIMEOUT_SEC:.1f}s={timeout_count}"
        )

    white_score = calc_white_score(
        white_result,
        side_move_counts[WHITE],
        stats[WHITE]["times"],
    )
    print(f"WHITE score: {white_score:.1f}")
    print(f"Move sequence: {''.join(move_sequence)}")


def main():
    args = parse_args()
    
    black = launch_engine([
        sys.executable, args.black
    ])
    
    white = launch_engine([
        sys.executable, args.white
    ])

    board = create_board(BOARD_SIZE)
    move_index_board = empty_move_index_board(BOARD_SIZE)
    side_move_counts = {BLACK: 0, WHITE: 0}
    timing_stats = init_stats()
    move_sequence = []
    white_result = "LOSE"

    players = {BLACK: black, WHITE: white}
    names = {BLACK: "BLACK", WHITE: "WHITE"}

    send_line(black, f"START {BOARD_SIZE} BLACK")
    send_line(white, f"START {BOARD_SIZE} WHITE")

    current = BLACK
    move_count = 0

    try:
        while True:
            proc = players[current]
            name = names[current]

            legal_now = legal_moves(board, current)
            if not legal_now:
                print(f"{name} has no legal moves")
                white_result = "LOSE" if current == WHITE else "WIN"
                safe_send_end(players[current], "LOSE")
                safe_send_end(players[opponent(current)], "WIN")
                break

            send_turn(proc, board)

            start_t = time.perf_counter()
            timed_out = False

            try:
                line = recv_line_with_timeout(proc, MOVE_TIMEOUT_SEC)
                x, y = parse_move(line)

                if not is_legal_move(board, x, y, current):
                    print(f"{name} illegal move: {coord_to_label(x, y)}")
                    white_result = "LOSE" if current == WHITE else "WIN"
                    safe_send_end(players[current], "LOSE")
                    safe_send_end(players[opponent(current)], "WIN")
                    break

            except TimeoutError:
                timed_out = True
                legal_now = legal_moves(board, current)
                if not legal_now:
                    print(f"{name} timeout and no legal substitute moves")
                    white_result = "LOSE" if current == WHITE else "WIN"
                    safe_send_end(players[current], "LOSE")
                    safe_send_end(players[opponent(current)], "WIN")
                    break
                x, y = random.choice(legal_now)
                print(
                    f"{name} timeout > {MOVE_TIMEOUT_SEC:.1f}s, "
                    f"referee random legal move -> {coord_to_label(x, y)}"
                )

            except Exception as e:
                print(f"{name} protocol/runtime error: {e}")
                white_result = "LOSE" if current == WHITE else "WIN"
                safe_send_end(players[current], "LOSE")
                safe_send_end(players[opponent(current)], "WIN")
                break

            elapsed = time.perf_counter() - start_t
            record_timing(timing_stats, current, elapsed, timed_out)

            board[y][x] = current
            side_move_counts[current] += 1
            move_index_board[y][x] = side_move_counts[current]
            move_count += 1

            move_label = coord_to_label(x, y)
            move_sequence.append(move_label)
            if timed_out:
                print(f"\nMove {move_count}: {name} -> {move_label}   [referee substitute, {elapsed:.3f}s]")
            else:
                print(f"\nMove {move_count}: {name} -> {move_label}   [{elapsed:.3f}s]")

            print(format_board_with_move_index(board, move_index_board))

            if is_win_after_move(board, x, y, current):
                print(f"\n{name} wins")
                white_result = "WIN" if current == WHITE else "LOSE"
                safe_send_end(players[current], "WIN")
                safe_send_end(players[opponent(current)], "LOSE")
                break

            if board_full(board):
                print("\nDRAW")
                white_result = "DRAW"
                safe_send_end(players[BLACK], "DRAW")
                safe_send_end(players[WHITE], "DRAW")
                break

            current = opponent(current)

    finally:
        print_match_stats(timing_stats, move_sequence, side_move_counts, white_result)
        for proc in [black, white]:
            try:
                proc.kill()
            except Exception:
                pass


if __name__ == "__main__":
    main()
