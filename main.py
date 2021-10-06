# todo:
#  basic menu, starting equipment choice dialogue
#  placeholder background music (e.g. crystal by m.o.o.n.)
#  boss.py, Troll boss
# After tech demo
# todo:
#  Sound system
#  split threads by Input+calculation // drawing OR try to draw less often after splitting input from drawing
#  try to update FPS_TICK by get_time

from scenario import *

print(frame_text([" FENCI "]))
print(f"Droppable weapons: {', '.join(Wielded.registry.keys())or 'None'}")
print(f"Droppable hats: {', '.join(Hat.registry.keys()) or 'None'}")
for tier in range(5):
    level = filter(lambda x: artifacts[x]["tier"] == tier, list(artifacts.keys()))
    print(f"Loaded artifacts at tier {tier}: {', '.join(level) or 'None'}")

sh = SceneHandler(1, [Goblin])
# sh = SceneHandler(1, [DebugGoblin], on_scren_enemies=[1, 1], loot_drops=10)
sh.player.equip(Spear(BASE_SIZE, tier_target=2), 'main_hand')
sh.player.equip(Shield(BASE_SIZE, tier_target=2), 'off_hand')
sh.scene.log_weapons()


while True:
    sh.execute()
