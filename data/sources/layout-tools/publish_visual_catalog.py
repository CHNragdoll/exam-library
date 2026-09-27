"""Install only the verified visual-catalog candidate and update local ZIPs."""
import publish_local
from visual_catalog_update import STAGE,BACKUP
publish_local.STAGE=STAGE
publish_local.BACKUP=BACKUP
publish_local.INSTALL_RECORD='visual-catalog-install.json'
publish_local.main()
