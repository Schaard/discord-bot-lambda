[1mdiff --git a/src/app/main.py b/src/app/main.py[m
[1mindex d3fcf16..1820971 100644[m
[1m--- a/src/app/main.py[m
[1m+++ b/src/app/main.py[m
[36m@@ -407,7 +407,8 @@[m [mdef interact(raw_request, active_entitlement):[m
                                             "style": 2,  # Short input[m
                                             "label": "Cause of Death (optional)",[m
                                             "placeholder": "What was the cause of death?",[m
[31m-                                            "required": False[m
[32m+[m[32m                                            "required": False,[m
[32m+[m[32m                                            "max_length": 250[m
                                         }[m
                                     ][m
                                 },[m
[36m@@ -420,7 +421,8 @@[m [mdef interact(raw_request, active_entitlement):[m
                                             "style": 2,  # Paragraph input (multi-line)[m
                                             "label": "Last Words (optional)",[m
                                             "placeholder": "What was said?",[m
[31m-                                            "required": False[m
[32m+[m[32m                                            "required": False,[m
[32m+[m[32m                                            "max_length": 250[m
                                         }[m
                                     ][m
                                 },[m
[36m@@ -433,7 +435,8 @@[m [mdef interact(raw_request, active_entitlement):[m
                                             "style": 1,  [m
                                             "label": "Link to Evidence (optional)",[m
                                             "placeholder": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",[m
[31m-                                            "required": False[m
[32m+[m[32m                                            "required": False,[m
[32m+[m[32m                                            "max_length": 250[m
                                         }[m
                                     ][m
                                 },[m
[36m@@ -460,7 +463,8 @@[m [mdef interact(raw_request, active_entitlement):[m
                                             "style": 2,  # Short input[m
                                             "label": "Cause of Death (optional)",[m
                                             "placeholder": "What was the cause of death?",[m
[31m-                                            "required": False[m
[32m+[m[32m                                            "required": False,[m
[32m+[m[32m                                            "max_length": 250[m
                                         }[m
                                     ][m
                                 },[m
[36m@@ -473,7 +477,8 @@[m [mdef interact(raw_request, active_entitlement):[m
                                             "style": 2,  # Paragraph input (multi-line)[m
                                             "label": "Last Words (optional)",[m
                                             "placeholder": "What was said over voice chat?",[m
[31m-                                            "required": False[m
[32m+[m[32m                                            "required": False,[m
[32m+[m[32m                                            "max_length": 250[m
                                         }[m
                                     ][m
                                 },[m
[36m@@ -486,7 +491,8 @@[m [mdef interact(raw_request, active_entitlement):[m
                                             "style": 1,  # Paragraph input (multi-line)[m
                                             "label": "Link to Evidence (optional)",[m
                                             "placeholder": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",[m
[31m-                                            "required": False[m
[32m+[m[32m                                            "required": False,[m
[32m+[m[32m                                            "max_length": 250[m
                                         }[m
                                     ][m
                                 },[m
[36m@@ -681,6 +687,7 @@[m [mdef interact(raw_request, active_entitlement):[m
                     last_words = data["components"][1]["components"][0]["value"][m
                     last_words = sanitize_input(last_words)[m
                     evidence_link = data["components"][2]["components"][0]["value"][m
[32m+[m[32m                    if len(evidence_link) > 2024: evidence_link = evidence_link[:2024][m
                     #unforgivable = interpret_boolean_input(unforgivable)[m
                     [m
                     #can't forgive your own oops [m
[36m@@ -730,7 +737,7 @@[m [mdef interact(raw_request, active_entitlement):[m
                             content_for_grudge_message += f"\nWith {user_kills} unforgiven deaths from {victim_name} and {compare_kills} in return, {end_of_kill_message} ({user_kills - compare_kills})"[m
                         else:[m
                             content_for_grudge_message += f"\nWith {compare_kills} unforgiven deaths from {user_name} and {user_kills} in return, {end_of_kill_message} ({compare_kills - user_kills})"[m
[31m-                        content_for_grudge_message += f"\n\n{user_name}: will you forgive or keep the grudge?"[m
[32m+[m[32m                        content_for_grudge_message += f"\n\n{user_name.capitalize()}: will you forgive or keep the grudge?"[m
                         [m
                         # Create an embed[m
                         embed = discord.Embed([m
[36m@@ -797,6 +804,7 @@[m [mdef interact(raw_request, active_entitlement):[m
                     last_words = data["components"][1]["components"][0]["value"][m
                     last_words = sanitize_input(last_words)[m
                     evidence_link = data["components"][2]["components"][0]["value"][m
[32m+[m[32m                    if len(evidence_link) > 500: evidence_link = evidence_link[:500][m
                     #unforgivable = interpret_boolean_input(unforgivable)[m
                     forgiven = False[m
                     #forgiven = interpret_boolean_input(forgiven)[m
