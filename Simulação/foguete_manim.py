"""Manim Community, renderer Cairo. Renderize com:
manim -qh foguete_manim.py Foguete
A imagem deve estar na vertical, com a ponta para cima, sem pluma.
CORTE é a altura da junta medida desde o topo da imagem sem margens transparentes.
As posições e comprimentos das setas são esquemáticos, sem escala comum.
"""
from pathlib import Path
import numpy as np
from PIL import Image
from manim import *

CORTE = 0.60
AR, PESO, MOTOR, VIOLETA = "#22d3ee", "#ff4d6d", "#ffb02e", "#a06bff"
TINTA, CINZA, VERDE = "#e9eef8", "#93a1ba", "#3ddc84"


def ponto(x, y):
    return np.array([x, y, 0.])


def simbolo(tex, x, y, cor=TINTA, tamanho=38):
    return MathTex(tex, font_size=tamanho, color=cor).move_to(ponto(x, y))


def vetor(x, y, dy, tex, cor, lado=RIGHT):
    seta = Arrow(ponto(x, y), ponto(x, y + dy), buff=0,
                 color=cor, stroke_width=5, max_tip_length_to_length_ratio=0.22)
    letra = MathTex(tex, font_size=36, color=cor).next_to(seta, lado, buff=0.14)
    return VGroup(seta, letra)


class Foguete(Scene):
    def construct(self):
        self.camera.background_color = "#000000"
        relativo = Path("media/assets/foguete.png")
        arquivo = Path(__file__).resolve().parent / relativo
        if not arquivo.exists():
            arquivo = relativo
        with Image.open(arquivo) as original:
            rgba = original.convert("RGBA")
            caixa = rgba.getchannel("A").getbbox()
            if caixa is None:
                raise ValueError("O PNG está totalmente transparente.")
            self.foto = np.array(rgba.crop(caixa))
        for cena in (self.forcas, self.arrasto, self.motor, self.separacao):
            self.next_section(cena.__name__)
            cena()
            self.play(*[FadeOut(obj) for obj in list(self.mobjects)], run_time=0.55)

    def nave(self, altura, x, y):
        obj = ImageMobject(self.foto).set_height(altura)
        if obj.width > 2.8:
            obj.set_width(2.8)
        return obj.move_to(ponto(x, y))

    def forcas(self):
        nave = self.nave(3.7, 0, 0)
        self.play(FadeIn(nave))
        x = nave.width / 2 + 0.30
        for seta in (
            vetor(-x, 0.15, 0.78, "E_a", AR, LEFT),
            vetor(-x, -0.15, -1.40, "P", PESO, LEFT),
            vetor(x, -0.15, -0.94, "F_D", VIOLETA),
            vetor(x, 0.15, 1.92, "T", MOTOR),
        ):
            self.play(GrowArrow(seta[0]), FadeIn(seta[1]), run_time=0.72)
            self.wait(0.45)
        self.wait(1.4)

    def arrasto(self):
        # Referencial do ar. Projeção oblíqua de um disco horizontal.
        # Cada ponto permanece parado até o disco alcançar sua altura.
        x, y0, curso, raio = -2.8, -1.65, 3.2, 0.96
        fase = ValueTracker(0)
        def proj(u, z, h):
            return ponto(x + u, y0 + h + 0.31*z)
        def disco(h, opacidade):
            return Ellipse(width=2*raio, height=0.62*raio,
                           color=AR, fill_opacity=opacidade, stroke_width=2
                           ).move_to(proj(0, 0, h))
        base, topo = disco(0, 0.04), disco(curso, 0.04)
        guias = VGroup(*[DashedLine(proj(s*raio, 0, 0), proj(s*raio, 0, curso),
                                    color=CINZA, stroke_width=1.3) for s in (-1, 1)])
        frente = disco(0, 0.23)
        frente.add_updater(lambda m: m.move_to(proj(0, 0, curso*fase.get_value())))
        nave = self.nave(1.55, x, y0)
        nave.add_updater(lambda m: m.move_to(frente.get_center() + DOWN*m.height/2))
        rng = np.random.default_rng(37)
        particulas = VGroup()
        for _ in range(72):
            u, z = rng.uniform(-1.48, 1.48, 2)
            h = rng.uniform(0.12, curso)
            dentro = u*u + z*z <= raio*raio
            dot = Dot(proj(u, z, h), radius=0.035, color=CINZA)
            def mover(m, u=u, z=z, h=h, dentro=dentro):
                avanco = max(0., curso*fase.get_value()-h) if dentro else 0.
                m.move_to(proj(u + np.sign(u)*0.72*avanco, z, h + 0.55*avanco))
                m.set_color(AR if avanco > 0 else CINZA)
            dot.add_updater(mover)
            particulas.add(dot)
        area = simbolo("A", x-1.35, y0, AR)
        area.add_updater(lambda m: m.set_y(frente.get_y()))
        self.play(FadeIn(guias), FadeIn(base), FadeIn(topo), FadeIn(particulas))
        self.add(nave, frente, area)
        self.play(fase.animate.set_value(1), run_time=4.2, rate_func=linear)
        for obj in (nave, frente, area, particulas):
            obj.clear_updaters()
        self.play(FadeIn(simbolo(r"\Delta V=A\,v_{\rm rel}\,\Delta t", 2.65, 1.35)),
                  FadeIn(vetor(x+1.65, 0.5, 1.0, r"v_{\mathrm{rel}}", VERDE)))
        self.wait(1.3)
        self.play(FadeIn(simbolo(r"F_D=\tfrac12 C_D(M)\,\rho(h)\,A\,v_{\rm rel}^2",
                                 2.65, -0.10, VIOLETA)),
                  FadeIn(vetor(x+1.65, 0.25, -1.0, "F_D", VIOLETA)))
        self.wait(2.5)

    def motor(self):
        nave = self.nave(2.8, -3.6, 0.7)
        b = nave.get_bottom()
        self.play(FadeIn(nave))
        # Corte esquemático ampliado do bocal, com uma linha-guia de ampliação.
        cx = 1.55
        perfil = [(0.55, 1.95), (0.55, 1.60), (0.22, 1.05),
                  (0.36, 0.55), (0.74, -0.28)]
        paredes = VGroup(*[VMobject(color=CINZA, stroke_width=4).set_points_as_corners(
            [ponto(cx+s*r, y) for r, y in perfil]) for s in (-1, 1)])
        guia = DashedLine(b, ponto(cx-0.74, -0.28), color=CINZA, stroke_width=1)
        self.play(Create(guia), Create(paredes))
        tempo = ValueTracker(0)
        gases = VGroup()
        for i in range(50):
            lateral = 0.83*np.sin(i*2.39996)
            def pos(t, lateral=lateral):
                y = 1.92 - 3.70*(0.55*t+0.45*t*t)
                largura = np.interp(y, [-1.8, -0.28, 0.55, 1.05, 1.60, 1.95],
                                    [1.00, 0.74, 0.36, 0.22, 0.55, 0.55])
                return ponto(cx + lateral*largura, y)
            dot = Dot(radius=0.042, color=MOTOR)
            def fluir(m, offset=i/50, pos=pos):
                t = (tempo.get_value()+offset) % 1
                m.move_to(pos(t)).set_opacity(min(1., 10*t, 10*(1-t)))
            dot.add_updater(fluir, call_updater=True)
            gases.add(dot)
        self.add(gases)
        empuxo = vetor(-4.65, 0, 1.60, "T", MOTOR, LEFT)
        fluxo = vetor(cx + 1.40, -0.3, -1.10, r"\mu_e", MOTOR)
        self.play(FadeIn(empuxo), FadeIn(fluxo), tempo.animate.set_value(2),
                  run_time=3.3, rate_func=linear)
        saida = DashedLine(ponto(cx-0.74, -0.28), ponto(cx+0.74, -0.28), color=AR)
        pressoes = VGroup(simbolo("P_e", cx-1.08, -0.23, AR),
                          simbolo("P_a", cx+1.43, -2.00, CINZA),
                          simbolo("Q=0", cx+2.05, 1.35, CINZA))
        formula = simbolo(r"T=c\left[\dot m\,\mu_e+(P_e-P_a)A_e\right]", 0, -2.95)
        self.play(Create(saida), FadeIn(pressoes), tempo.animate.set_value(3.5),
                  run_time=2.5, rate_func=linear)
        self.play(Write(formula), tempo.animate.set_value(5.5), run_time=3.3, rate_func=linear)
        gases.clear_updaters()

    def separacao(self):
        # Referencial instantâneo do centro de massa. O balanço de energia
        # usa apenas a parcela da energia interna convertida em movimento relativo.
        nave = self.nave(3.45, -2.75, 0)
        self.play(FadeIn(nave))
        h, w = self.foto.shape[:2]
        linha = int(np.clip(round(h*CORTE), 1, h-1))
        escala = nave.height / h
        partes = []
        for inicio, fim in ((0, linha), (linha, h)):
            obj = ImageMobject(self.foto[inicio:fim].copy()).set_width(nave.width)
            obj.move_to(nave.get_top() + DOWN*escala*(inicio+fim)/2)
            partes.append(obj)
        superior, inferior = partes
        junta = superior.get_bottom()
        self.remove(nave)
        self.add(superior, inferior)
        estado = simbolo(r"(m,\,A,\,V)", 2.40, 1.70)
        self.play(FadeIn(estado), Flash(junta, color=MOTOR, flash_radius=0.43))
        self.play(superior.animate.shift(0.55*UP), inferior.animate.shift(1.10*DOWN),
                  run_time=1.5, rate_func=linear)
        self.play(Transform(estado, simbolo(r"(m_1,\,A_1,\,V_1)", 2.4, 1.7, VERDE)),
                  FadeIn(vetor(-3.05-nave.width/2, 0.90, 0.55, r"\Delta v_1", VERDE, LEFT)),
                  FadeIn(vetor(-3.05-nave.width/2, -1.05, -1.10, r"\Delta v_2", AR, LEFT)))
        self.play(Write(simbolo(r"m_1\Delta v_1+m_2\Delta v_2=0", 2.4, 0.40)))
        self.play(Write(simbolo(r"\Delta K=\tfrac12 m_1(\Delta v_1)^2"
                                r"+\tfrac12 m_2(\Delta v_2)^2", 2.4, -0.85, MOTOR, 34)))
        self.wait(2.8)
