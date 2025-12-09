using Xunit;

namespace Liberap.EntityFrameworkCore;

[CollectionDefinition(LiberapTestConsts.CollectionDefinitionName)]
public class LiberapEntityFrameworkCoreCollection : ICollectionFixture<LiberapEntityFrameworkCoreFixture>
{

}
