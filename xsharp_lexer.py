from enum import Enum
from xsharp_helper import Position, UnexpectedCharacter, UnknownImport
import string
from os.path import exists
import re

KEYWORDS = [
	"const", "var",
	"for", "start", "end", "step",
	"while",
	"if", "elseif", "else",
	#"include",
	"sub"
]
DATA_TYPES = [
	"int", "bool"
]

# Token types
class TT(Enum):
	LT, LE, EQ, NE, GT, GE,\
	ADD, SUB, INC, DEC,\
	AND, OR, NOT, XOR,\
	LPR, RPR, LBR, RBR, LSQ, RSQ,\
	COL, ASSIGN, COMMA,\
	MUL, DIV, RSHIFT, LSHIFT,\
	ABS, SIGN, AT,\
	NUM, IDENTIFIER, KEYWORD, NEWLINE, EOF\
	= range(35)

	def __str__(self):
		return super().__str__().removeprefix("TT.")

token_patterns = {}

class Token:
	def __init__(self, start_pos: Position, end_pos: Position, token_type: TT, value: str|int|None = None):
		self.start_pos = start_pos
		self.end_pos = end_pos
		self.token_type = token_type
		self.value = value
	
	def __repr__(self):
		if self.value: return f"{self.token_type}:{self.value}"
		return f"{self.token_type}"

	def __eq__(self, value):
		if isinstance(value, Token):
			return self.value == value.value and self.token_type == value.token_type
		return False
	
	def __ne__(self, value):
		return not (self.__eq__(value))

class Lexer:
	def __init__(self, fn: str, ftxt: str, running_from_bot: bool = False):
		self.fn = fn
		self.ftxt = ftxt
		self.rest = ftxt
		self.from_bot = running_from_bot

		self.tokens: list[Token] = []

		self.pos = Position(-1, 0, -1, fn, ftxt)
		self.libraries: list[str] = []
		self.imported: set = set()
		self.advance()

	# Advance to the next character
	def advance(self):
		self.pos.advance(self.rest[0] if self.rest else None)
		self.rest = self.rest[1:]

	# advance by length
	def advance_by(self, by: re.Match):
		self.pos.advance_by(by)
		self.rest = self.rest[by.end():]

	# Standard libraries
	def process_file(self, contents: str|None = None):
		if contents:
			txt_lines = contents.splitlines()
		else:
			txt_lines = self.ftxt.splitlines()

		result: list[str] = [
			j.strip()
			for i in txt_lines
			for j in i.split(";")
		]

		libraries: list[str] = []
		files: list[str] = []
		
		for line in result:
			line = line.split("//")[0].strip()
			if line.startswith("include "):
				libraries += line[7:].replace(" ", "").split(",")
		
		for lib in libraries:
			if lib.endswith(".xs") and exists(f"programs/{lib}"):
				if self.from_bot:
					index = self.ftxt.index(f"{lib}")
					start_pos = Position(
						index, self.ftxt[:index].count("\n"), 8, self.fn, self.ftxt
					)
					end_pos = Position(
	    				index + len(lib), self.ftxt[:index].count("\n"), 8, self.fn, self.ftxt
          			)
					return UnknownImport(start_pos, end_pos, f"{lib} (cannot import files when running from Compilation Bot)")
				
				files.append(lib)
			elif lib == "operations":
				pass  # Built-in library, no file needed
			else:
				index = self.ftxt.index(f"{lib}")
				start_pos = Position(
					index, self.ftxt[:index].count("\n"), 8, self.fn, self.ftxt
				)
				end_pos = Position(
					index + len(lib), self.ftxt[:index].count("\n"), 8, self.fn, self.ftxt
				)
				return UnknownImport(start_pos, end_pos, lib)
		
		module_txt: str = ""
		for file in files:
			if file in self.imported:
				continue
			with open(f"programs/{file}", "r") as module:
				self.imported.add(file)
				contents = module.read()
				if contents == self.ftxt:
					print("Skipping self-import off:", file)
					continue
				text = ";".join(contents.splitlines())
				self.process_file(text)
				module_txt += text + "\n"
		print(f"{module_txt= }")
		self.ftxt = module_txt + self.ftxt

	# Lexes the file text and returns a list of tokens
	def lex(self):
		self.tokens: list[Token] = []

		lib_error = self.process_file()
		if lib_error is not None:
			return None, lib_error
		
		# Reinitialize, as this messes up the current character
		self.pos = Position(-1, 0, -1, self.fn, self.ftxt)
		print(f"{self.ftxt= }")
		self.rest = " " + self.ftxt
		self.advance()

		while not self.rest == "":
			print(f"{self.rest= }")
			# handling include statemnets
			# include = re.match(r"include [\w ,\.]*", self.rest)
			# if include:
			# 	print(f"{include= }")
			# 	self.advance_by(include)
			# 	continue

			# handling whitespace
			whitespace = re.match(r"[\t ]+", self.rest)
			if whitespace:
				print(f"{whitespace= }")
				self.advance_by(whitespace)
				continue


			patterns = [(rule_func, re.match(pattern, self.rest)) for pattern, rule_func in token_patterns.items()]
			matches = [(rule_func, match) for rule_func, match in patterns if match]
			matches.sort(key=lambda e: len(e[1].group()), reverse=True)
			print(f"{(matches[0][1].re if len(matches) > 0 else None)} {matches=}")
			start_pos = self.pos.copy()
			if matches == []:
				self.advance()
				return None, UnexpectedCharacter(start_pos, self.pos, f"'{self.rest[0:]}'")
			
			matched = matches[0]
			
			matched[0](self, matched[1])


		print(f"{self.rest= }")
		
		self.tokens.append(Token(self.pos, self.pos, TT.EOF))
		print(f"{self.tokens= }")
		return self.tokens, None


def push(token_type: TT):
	def push_token(lexer: Lexer, matched: re.Match):
		lexer.advance_by(matched)
		start_pos = lexer.pos.copy()
		lexer.tokens.append(Token(start_pos, lexer.pos, token_type, *matched.groups()))

	return push_token

def skip():
	def handle_include(lexer: Lexer, matched: re.Match):
		lexer.advance_by(matched)
	return handle_include

token_patterns = {
	re.compile(r"<"): 			push(TT.LT),
	re.compile(r"<="):			push(TT.LE),
	re.compile(r"=="): 			push(TT.EQ),
	re.compile(r"!="): 			push(TT.NE),
	re.compile(r">"): 			push(TT.GT),
	re.compile(r">="): 			push(TT.GE),
	re.compile(r"\+"): 			push(TT.ADD),
	re.compile(r"-"): 			push(TT.SUB),
	re.compile(r"\*"): 			push(TT.MUL),
	re.compile(r"\/"): 			push(TT.DIV),
	re.compile(r"\+\+"): 		push(TT.INC),
	re.compile(r"--"):			push(TT.DEC),
	re.compile(r"&"): 			push(TT.AND),
	re.compile(r"\|"):			push(TT.OR),
	re.compile(r"~"): 			push(TT.NOT),
	re.compile(r"\^"):			push(TT.XOR),
	re.compile(r"\("):			push(TT.LPR),
	re.compile(r"\)"):			push(TT.RPR),
	re.compile(r"\{"):			push(TT.LBR),
	re.compile(r"\}"):			push(TT.RBR),
	re.compile(r"\["):			push(TT.LSQ),
	re.compile(r"\]"):			push(TT.RSQ),
	re.compile(r":"): 			push(TT.COL),
	re.compile(r"="): 			push(TT.ASSIGN),
	re.compile(r","): 			push(TT.COMMA),
	re.compile(r">>"):			push(TT.RSHIFT),
	re.compile(r"<<"):			push(TT.LSHIFT),
	re.compile(r"#"): 			push(TT.ABS),
	re.compile(r"\$"): 			push(TT.SIGN),
	re.compile(r"@"): 			push(TT.AT),
	re.compile(r"(\d+)"): 		push(TT.NUM),
	re.compile("("+"|".join(KEYWORDS+DATA_TYPES)+")"):
								push(TT.KEYWORD),
	re.compile(r"include (operations)"):
								skip(),
	re.compile(r"include\s+([\w]+\.xs(?:\s*,\s*[\w]+\.xs)*)"): # import files
							skip(),
	
	re.compile(r"(\w[\w\d]*)"):			push(TT.IDENTIFIER),
	re.compile(r"(\n|\t|;)"): 			push(TT.NEWLINE),
	re.compile(r"//[^\r\n]*[\n\r]"):	skip(),  # Single-line comment
	re.compile(r"/\*[\s\S]*?\*/"): 		skip(),  # Multi-line comment
	re.compile(r"[\r\n\t ]+"): 			skip(),  # Whitespace
}