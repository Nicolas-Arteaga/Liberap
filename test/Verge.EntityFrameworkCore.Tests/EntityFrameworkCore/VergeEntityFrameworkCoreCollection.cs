using Xunit;

namespace Verge.EntityFrameworkCore;

[CollectionDefinition(VergeTestConsts.CollectionDefinitionName)]
public class VergeEntityFrameworkCoreCollection : ICollectionFixture<VergeEntityFrameworkCoreFixture>
{

}
