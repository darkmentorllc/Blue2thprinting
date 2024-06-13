extern struct obex_plugin_desc __obex_builtin_filesystem;
extern struct obex_plugin_desc __obex_builtin_bluetooth;
extern struct obex_plugin_desc __obex_builtin_pcsuite;
extern struct obex_plugin_desc __obex_builtin_opp;
extern struct obex_plugin_desc __obex_builtin_ftp;
extern struct obex_plugin_desc __obex_builtin_irmc;
extern struct obex_plugin_desc __obex_builtin_pbap;
extern struct obex_plugin_desc __obex_builtin_mas;
extern struct obex_plugin_desc __obex_builtin_mns;

static struct obex_plugin_desc *__obex_builtin[] = {
  &__obex_builtin_filesystem,
  &__obex_builtin_bluetooth,
  &__obex_builtin_pcsuite,
  &__obex_builtin_opp,
  &__obex_builtin_ftp,
  &__obex_builtin_irmc,
  &__obex_builtin_pbap,
  &__obex_builtin_mas,
  &__obex_builtin_mns,
  NULL
};
