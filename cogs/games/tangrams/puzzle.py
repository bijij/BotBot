class Piece:
    def __init__(self, state: list[list[bool]]):
        self.state = state

    def __getitem__(self, ij):
        i, j = ij
        return self.state[j][i]

    @classmethod
    def from_string(cls, char: str, piece: list[str]):
        return cls([[col == char for col in row] for row in piece])


class Board:
    def __init__(self, state: list[list[bool]], pieces: list[Piece]):
        self.state = state
        self.pieces = pieces

    def __getitem__(self, ij):
        i, j = ij
        return self.state[j][i]

    def test_solution(self, positions: list[tuple[int, int]]) -> bool:
        if len(positions) != len(self.pieces):
            raise ValueError("You're bad")

        state = [[False for col in row] for row in self.state]

        for piece, position in zip(self.pieces, positions):
            for y, row in enumerate(piece.state, position[1]):
                for x, col in enumerate(row, position[0]):
                    state[y][x] = max(state[y][x], col)

        return state == self.state

    @classmethod
    def from_string(cls, board: list[str]):
        piece_count = len(set("".join(board))) - 1
        pieces: list[Piece] = []

        for i in range(piece_count):
            char = chr(ord("a") + i)
            rows = [row for row in board if char in row]

            # Determine columns
            min_x = len(board[0])
            for row in rows:
                for x, col in enumerate(row):
                    if col == char:
                        min_x = min(x, min_x)
                        break
            max_x = 0
            for row in rows:
                for x, col in enumerate(reversed(row)):
                    if col == char:
                        max_x = max(len(row) - x, max_x)
                        break

            pieces.append(Piece.from_string(char, [row[min_x:max_x] for row in rows]))

        return cls([[col != "-" for col in row] for row in board], pieces)
