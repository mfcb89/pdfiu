"""Parse the optional advanced PDF search syntax."""

import re

from translations import tr


TOKENS = re.compile(r'"[^"]*"|[()]|[^\s()"]+|"')
OPERATORS = {"AND", "OR", "NOT"}


class SearchSyntaxError(ValueError):
    pass


class SearchQuery:
    def __init__(self, query):
        self.tokens = TOKENS.findall(query)
        self.position = 0
        if len(self.tokens) > 64:
            raise SearchSyntaxError(tr("La búsqueda avanzada admite hasta 64 elementos. Acorta la consulta."))
        if '"' in self.tokens:
            raise SearchSyntaxError(tr("Cierra las comillas para buscar la frase."))
        self.tree = self.parse_or()
        if self.peek() is not None:
            raise SearchSyntaxError(tr("Revisa los paréntesis y los operadores de la consulta."))

    def peek(self):
        return self.tokens[self.position] if self.position < len(self.tokens) else None

    def take(self):
        token = self.peek()
        self.position += 1
        return token

    def parse_or(self):
        result = self.parse_and()
        while self.peek() == "OR":
            self.take()
            result = ("OR", result, self.parse_and())
        return result

    def parse_and(self):
        result = self.parse_operand()
        while self.peek() not in (None, ")", "OR"):
            if self.peek() == "AND":
                self.take()
            result = ("AND", result, self.parse_operand())
        return result

    def parse_operand(self):
        token = self.take()
        if token == "NOT":
            child = self.parse_operand()
            return child[1] if child[0] == "NOT" else ("NOT", child)
        if token == "(":
            child = self.parse_or()
            if self.take() != ")":
                raise SearchSyntaxError(tr("Cierra el paréntesis para completar la consulta."))
            return child
        if token is None or token == ")" or token in OPERATORS:
            raise SearchSyntaxError(tr("Falta una palabra o frase en la consulta."))
        quoted = token.startswith('"')
        term = " ".join((token[1:-1] if quoted else token).split())
        if not term:
            raise SearchSyntaxError(tr("Escribe una palabra o frase entre las comillas."))
        return ("TERM", (term, quoted))

    def matching_terms(self, contains):
        """Return matching positive terms, or None if the page fails the query."""
        def evaluate(node):
            operator, left, *rest = node
            if operator == "TERM":
                return {left} if contains(left) else None
            lhs = evaluate(left)
            if operator == "NOT":
                return set() if lhs is None else None
            if operator == "AND" and lhs is None:
                return None
            rhs = evaluate(rest[0])
            if operator == "AND" and rhs is None:
                return None
            if lhs is None and rhs is None:
                return None
            return (lhs or set()) | (rhs or set())

        return evaluate(self.tree)
