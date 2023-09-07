class Checker:
    def __init__(self, color):
        self.color = color
        self.is_king = False

    def __str__(self):
        if self.color == 'black':
            if self.is_king:
                return 'B'
            else:
                return 'b'
        else:
            if self.is_king:
                return 'W'
            else:
                return 'w'


class Board:
    def __init__(self):
        self.board = []
        self.black_left = self.white_left = 12
        self.black_kings = self.white_kings = 0
        self.create_board()

    def create_board(self):
        for row in range(8):
            self.board.append([])
            for col in range(8):
                if row < 3:
                    if (row + col) % 2 == 0:
                        self.board[row].append(Checker('white'))
                    else:
                        self.board[row].append(None)
                elif row > 4:
                    if (row + col) % 2 == 0:
                        self.board[row].append(Checker('black'))
                    else:
                        self.board[row].append(None)
                else:
                    self.board[row].append(None)

    def draw_board(self):
        for row in range(8):
            for col in range(8):
                if self.board[row][col]:
                    print(self.board[row][col], end=' ')
                else:
                    if (row + col) % 2 == 0:
                        print('-', end=' ')
                    else:
                        print(' ', end=' ')
            print()

    def move(self, start, end):
        row1, col1 = start
        row2, col2 = end
        checker = self.board[row1][col1]
        if not checker:
            return False
        if not self.is_valid_move(start, end):
            return False
        if self.board[row2][col2]:
            self.remove_checker(row2, col2)
        self.board[row2][col2] = checker
        self.board[row1][col1] = None
        if row2 == 0 and checker.color == 'black':
            checker.is_king = True
            self.black_kings += 1
        if row2 == 7 and checker.color == 'white':
            checker.is_king = True
            self.white_kings += 1
        return True

    def is_valid_move(self, start, end):
        row1, col1 = start
        row2, col2 = end
        checker = self.board[row1][col1]
        if not checker:
            return False
        if self.board[row2][col2]:
            return False
        if checker.is_king or checker.color == 'black':
            if row2 < row1:
                return False
        else:
            if row2 > row1:
                return False
        if abs(row2 - row1) == 1 and abs(col2 - col1) == 1:
            return True
        if abs(row2 - row1) == 2 and abs(col2 - col1) == 2:
            mid_row = (row1 + row2) // 2
            mid_col = (col1 + col2) // 2
            if not self.board[mid_row][mid_col]:
                return False
            if self.board[mid_row][mid_col].color == checker.color:
                return False
            return True
        return False

    def remove_checker(self):
