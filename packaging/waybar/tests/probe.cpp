// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Robert R Green and contributors
#include "shelf_popup.hpp"
#include <iostream>
#include <string>

int main(int argc, char **argv) {
  using namespace waybar::util::shelf;
  if (argc > 1 && std::string(argv[1]) == "format") {
    std::cout << message(true, "DP-1\"\\\n\t\r\b\f", "menu\"\\\n") << '\n';
    std::cout << message(false, "显示-1", "1-2") << '\n';
    std::cout << (message(true, std::string(129, 'a'), "x").empty()
                      ? "bounded\n"
                      : "FAIL\n");
    return 0;
  }
  if (argc > 1 && std::string(argv[1]) == "send") {
    std::cout << (notify(true, "fixture-1") ? "sent" : "miss") << '\n';
    return 0;
  }
  gtk_init(&argc, &argv);
  GtkWidget *window = gtk_window_new(GTK_WINDOW_TOPLEVEL);
  gtk_window_set_default_size(GTK_WINDOW(window), 320, 240);
  GtkWidget *menu = gtk_menu_new();
  gtk_widget_set_size_request(menu, 240, 80);
  GtkWidget *parent = gtk_menu_item_new_with_label("Parent");
  GtkWidget *nested = gtk_menu_new();
  gtk_widget_set_size_request(nested, 220, 60);
  gtk_menu_shell_append(GTK_MENU_SHELL(nested),
                        gtk_menu_item_new_with_label("Nested"));
  gtk_menu_item_set_submenu(GTK_MENU_ITEM(parent), nested);
  gtk_menu_shell_append(GTK_MENU_SHELL(menu), parent);
  track_menu(menu);
  track_menu(menu); // Idempotence must not duplicate map notifications.
  gtk_widget_show_all(window);
  gtk_widget_show_all(menu);
  gtk_widget_show_all(nested);
  while (gtk_events_pending())
    gtk_main_iteration();
  gtk_menu_popup(GTK_MENU(menu), nullptr, nullptr, nullptr, nullptr, 0,
                 GDK_CURRENT_TIME);
  while (gtk_events_pending())
    gtk_main_iteration();
  // Mapping/unmapping is real GTK surface state in an isolated Broadway server;
  // no user display, pointer operation or compositor session is involved.
  gtk_menu_popup(GTK_MENU(nested), nullptr, nullptr, nullptr, nullptr, 0,
                 GDK_CURRENT_TIME);
  while (gtk_events_pending())
    gtk_main_iteration();
  gtk_menu_popdown(GTK_MENU(nested));
  gtk_menu_popdown(GTK_MENU(menu));
  while (gtk_events_pending())
    gtk_main_iteration();
  // Dynamically added submenu and assignment after attach.
  GtkWidget *later_item = gtk_menu_item_new_with_label("Later");
  gtk_menu_shell_append(GTK_MENU_SHELL(menu), later_item);
  GtkWidget *later = gtk_menu_new();
  gtk_widget_set_size_request(later, 220, 60);
  gtk_menu_shell_append(GTK_MENU_SHELL(later),
                        gtk_menu_item_new_with_label("Child"));
  gtk_menu_item_set_submenu(GTK_MENU_ITEM(later_item), later);
  gtk_widget_show_all(menu);
  gtk_menu_popup(GTK_MENU(later), nullptr, nullptr, nullptr, nullptr, 0,
                 GDK_CURRENT_TIME);
  while (gtk_events_pending())
    gtk_main_iteration();
  gtk_widget_destroy(later); // Active destruction must emit one matching close.
  gtk_widget_destroy(menu);
  gtk_widget_destroy(window);
  while (gtk_events_pending())
    gtk_main_iteration();
  return 0;
}
