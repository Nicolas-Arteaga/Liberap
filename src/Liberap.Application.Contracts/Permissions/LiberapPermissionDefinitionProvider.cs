using Liberap.Localization;
using Volo.Abp.Authorization.Permissions;
using Volo.Abp.Localization;
using Volo.Abp.MultiTenancy;

namespace Liberap.Permissions;

public class LiberapPermissionDefinitionProvider : PermissionDefinitionProvider
{
    public override void Define(IPermissionDefinitionContext context)
    {
        var myGroup = context.AddGroup(LiberapPermissions.GroupName);

        //Define your own permissions here. Example:
        //myGroup.AddPermission(LiberapPermissions.MyPermission1, L("Permission:MyPermission1"));
    }

    private static LocalizableString L(string name)
    {
        return LocalizableString.Create<LiberapResource>(name);
    }
}
