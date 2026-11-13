import pygame

pygame.init()
tela = pygame.display.set_mode((900, 700))
pygame.display.set_caption("Janela Preta")
relogio = pygame.time.Clock()

rodando = True
while rodando:
    for evento in pygame.event.get():
        if evento.type == pygame.QUIT:
            rodando = False
        elif evento.type == pygame.KEYDOWN and evento.key == pygame.K_ESCAPE:
            rodando = False

    tela.fill((0, 0, 0))
    pygame.display.flip()
    relogio.tick(60)

pygame.quit()
